import json
import os
import re
import uuid
from typing import List, Tuple, Optional, Literal, cast, Set
from urllib.parse import urlparse

import numpy as np
import weaviate
from llama_index.core.postprocessor import LLMRerank, SentenceTransformerRerank
from llama_index.core.schema import TextNode, NodeWithScore, QueryBundle
from pymongo.synchronous.collection import Collection
from scipy.spatial.distance import cosine

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.knowledge.vector import VectorizerService
from app.services.knowledge.vector.similarity_score_service import SimilarityScoreService
from app.utils.llama_index.llm_interaction import AzureOpenAILlamaIndexLLM, OllamaLlamaIndexLLM
from app.utils.llama_index.tilde_reranker import TILDEv2Reranker
from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)

DEDUPLICATE_PROMPT = """You are assisting with deduplicating clinical guideline passages.
- Goal: Keep a subset of passages that are NON-DUPLICATES.
- Drop any passage that is
    1. a semantic near-duplicate of another passage in this list
    2. substantially overlaps content with another passage in the list
- Preserve diversity of content and keep the clearest representative when passages overlap
- Return STRICT JSON with keys: keep (array of item_ids) and drop (array of objects with item_id and reason).

Respond with JSON ONLY. Example format:
{{
    "keep": [0, 3, 5],
    "drop": [
        {{"item_id": 1, "reason": "duplicate of 0"}},
        {{"item_id": 2, "reason": "irrelevant"}},
        {{"item_id": 4, "reason": "overlaps already-used"}}
    ]
}}

Passages:
{passages}
"""


class AdvancedDBService:
    """Combining weaviate AND LLamaIndex"""
    
    def __init__(self, vector_dbs_collection: Collection, vectorizer_service: VectorizerService, similarity_service: SimilarityScoreService):
        self.vectorizer_service = vectorizer_service
        self.vector_dbs_collection = vector_dbs_collection
        self.similarity_service = similarity_service
        
        weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8081")
        parsed = urlparse(weaviate_url)
        self.client = weaviate.connect_to_custom(
            http_host=parsed.hostname, http_port=parsed.port, http_secure=parsed.scheme == "https",
            grpc_host=parsed.hostname, grpc_port=50051, grpc_secure=parsed.scheme == "https",
        )
        self.client.connect()
    
    @staticmethod
    def filter_top_n_and_threshold(
            retrieved_chunks: List[WeaviateSearchChunkResult],
            top_n: Optional[int] = None,
            threshold: Optional[float] = None,
    ):
        """
        Based on !!RERANK score!!, apply filter of top n or certain threshold.
        - Requires the rerank score to be sortable
        - If using threshold: rerank score must be applicable to comparison with float
        """
        if top_n is None and threshold is None:
            raise ValueError("Either top_n or threshold must be set.")
        
        logger.debug(f"[Filter] top_n={top_n}, threshold={threshold}, input={len(retrieved_chunks)}")
        filtered_chunks = sorted(retrieved_chunks, key=lambda c: c.rerank_score, reverse=True)
        
        if top_n is not None:
            filtered_chunks = filtered_chunks[:top_n]
        if threshold is not None:
            filtered_chunks = [c for c in filtered_chunks if c.rerank_score >= threshold]
        
        logger.info(
            f"[Filter] Output={len(filtered_chunks)} (from {len(retrieved_chunks)}) | "
            f"top_n={top_n}, threshold={threshold}",
        )
        return filtered_chunks
    
    def filter_duplicates(
            self, retrieved_chunks: List[WeaviateSearchChunkResult], keep_all_guidelines=True, compared_property="text",
            rank_method: str = "cross_encoding", cutoff_similarity: float = 0.95, **kwargs,
    ):
        """
        Deduplicates by reranking (with options available for rerank function) compared to existing chunk
        - Always keeps the chunk that is listed first
        """
        if rank_method not in {"embedding", "cross_encoding", "llm"}:
            raise ValueError(
                f"Unsupported rank_method for duplication filtering: {rank_method}. Use one of: embedding, cross_encoding, llm.",
            )
        
        def _hash_dict(d: dict) -> int:
            return hash(tuple(sorted(d.items())))
        
        def deduplicate(chunks):
            if len(chunks) <= 1:
                return chunks
            
            remaining = list(chunks)
            kept: List[WeaviateSearchChunkResult] = []
            logger.debug(
                f"[Dedup] Start group with {len(chunks)} chunks | keep_all_guidelines={keep_all_guidelines} "
                f"| method={rank_method} | cutoff={cutoff_similarity}",
            )
            
            while remaining:
                current = remaining.pop(0)
                kept.append(current)
                if not remaining:
                    break
                compare_text = current.retrieved_chunk[compared_property]
                rerank_kwargs = dict(kwargs)
                if rank_method == "embedding":
                    rerank_kwargs["embedded_property"] = compared_property
                else:
                    rerank_kwargs["compared_property"] = compared_property
                
                others = list(remaining)
                reranked = self.rerank(
                    reranking_option=rank_method,
                    query=compare_text,
                    retrieved_chunks=others,
                    **rerank_kwargs,
                )
                dup_keys = {
                    _hash_dict(rc.retrieved_chunk)
                    for rc in reranked
                    if getattr(rc, "rerank_score", None) is not None
                       and float(rc.rerank_score) >= float(cutoff_similarity)
                }
                
                if dup_keys:
                    remaining = [
                        c for c in remaining if _hash_dict(c.retrieved_chunk) not in dup_keys
                    ]
                    logger.debug(
                        f"[Dedup] Removed {len(dup_keys)} duplicates vs current | "
                        f"current={compare_text[:15]}...",
                    )
            
            return kept
        
        def deduplicate_with_llm(
                chunks: List[WeaviateSearchChunkResult],
                llm_model: str,
                llm_api_key: Optional[str] = None,
                llm_api_base: Optional[str] = None,
                max_batch_size: int = 60,
        ):
            if len(chunks) <= 1:
                return chunks
            
            llm_model = cast(Literal["gpt-5", "gpt-4.1", "o3", "llama3_3-70b"], llm_model)
            llm = self._select_llm(
                model=llm_model, api_key=llm_api_key, api_base=llm_api_base,
            )
            
            def _batches(seq, n):
                for i in range(0, len(seq), n):
                    yield seq[i:i + n]
            
            kept_global_ids: Set[int] = set()
            id_by_order = {i: c for i, c in enumerate(chunks)}
            
            def build_prompt(items: List[Tuple[int, WeaviateSearchChunkResult]]) -> str:
                listing = []
                for i, c in items:
                    txt = (c.retrieved_chunk[compared_property]).replace("\n", " ").strip()
                    listing.append(
                        f"- item_id={i}: {txt}",
                    )
                return DEDUPLICATE_PROMPT.format(passages='\n'.join(listing))
            
            for batch in _batches(list(enumerate(retrieved_chunks)), max_batch_size):
                prompt = build_prompt(batch)
                raw = llm.complete(prompt).text.strip()
                # Try to extract/parse JSON robustly
                try:
                    m = re.search(r"\{.*\}", raw, flags=re.S)
                    raw_json = m.group(0) if m else raw
                    payload = json.loads(raw_json)
                except Exception as e:
                    logger.warning(f"[Dedup][LLM] JSON parse failed, keeping all in batch. Error: {e}")
                    kept_global_ids.update(i for i, _ in batch)
                    continue
                
                keep_ids = set(payload.get("keep", []))
                drop_list = payload.get("drop", [])
                logger.debug(
                    f"[Dedup][LLM] Batch result | keep={len(keep_ids)} | drop={len(drop_list)}",
                )
                kept_global_ids.update(int(i) for i in keep_ids if i in dict(batch))
            
            kept_chunks: List[WeaviateSearchChunkResult] = [
                id_by_order[i] for i in sorted(kept_global_ids) if i in id_by_order
            ]
            logger.info(
                f"[Dedup][LLM] Kept {len(kept_chunks)} / {len(retrieved_chunks)} after LLM dedup",
            )
            return kept_chunks
        
        filtered_chunks = []
        if keep_all_guidelines:
            chunks_per_guideline = {}
            for chunk in retrieved_chunks:
                guideline = chunk.retrieved_chunk["guideline_id"]
                chunks_per_guideline.setdefault(guideline, []).append(chunk)
            
            for _, gl_chunks in chunks_per_guideline.items():
                if rank_method == "llm":
                    filtered = deduplicate_with_llm(gl_chunks, **kwargs)
                else:
                    filtered = deduplicate(gl_chunks)
                
                filtered_chunks.extend(filtered)
        else:
            if rank_method == "llm":
                filtered_chunks = deduplicate_with_llm(retrieved_chunks, **kwargs)
            else:
                filtered_chunks = deduplicate(retrieved_chunks)
        
        removed = len(retrieved_chunks) - len(filtered_chunks)
        logger.info(
            f"[Dedup] Input={len(retrieved_chunks)} → Output={len(filtered_chunks)} | Removed={removed} "
            f"| keep_all_guidelines={keep_all_guidelines}",
        )
        return filtered_chunks
    
    @staticmethod
    def available_rerankings():
        # Did NOT find any useful clinical relevance score; given the evaluation problems, will also not attempt to use LLM (MAYBE INCLUDE, but can also ignore)
        return ["llm", "embedding", "cross_encoding", "tilde", "property_forward", "weighted_sum", "concatenate"]
    
    def rerank(self, reranking_option, **kwargs) -> List[WeaviateSearchChunkResult]:
        """
        Always descending, according to the newly calculated relevance score.
        """
        run_id = kwargs.pop("run_id", str(uuid.uuid4()))
        logger.info(f"[Rerank] Start option={reranking_option} | run_id={run_id}")
        if reranking_option == "llm":
            return self._llm_rerank(**kwargs)
        elif reranking_option == "embedding":
            return self._embedding_rerank(**kwargs)
        elif reranking_option == "cross_encoding":
            return self._cross_encoding_rerank(**kwargs)
        elif reranking_option == "tilde":
            # TESTED TILDE BUT HORRIBLE RESULTS, does not work for German
            return self._tilde_rerank(**kwargs)
        elif reranking_option == "property_forward":
            return self._property_based_rerank(**kwargs)
        elif reranking_option == "weighted_sum":
            return self._weighted_sum_rerank(**kwargs)
        elif reranking_option == "concatenate":
            return self._concatenated_score_rerank(**kwargs)
        else:
            raise ValueError(f"Unknown reranking option: {reranking_option}")
    
    @staticmethod
    def _call_llm(llm, prompt: str):
        try:
            llm_response = llm.complete(prompt)  # returns a string
        except AttributeError:
            llm_response = llm.predict(prompt)
        
        if not isinstance(llm_response, str):
            llm_text = getattr(llm_response, "text", "")
        else:
            llm_text = llm_response
        return llm_text
    
    @staticmethod
    def _select_llm(
            *, model: Literal["gpt-5", "gpt-4.1", "o3", "llama3_3-70b"], api_key: Optional[str] = None,
            api_base: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 2048, **kwargs,
    ):
        """Create a LlamaIndex LLM instance per your setup snippet."""
        if model in ("gpt-4.1", "o3", "gpt-5"):
            api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
            api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
            api_base = api_base or os.getenv("AZURE_OPENAI_API_BASE", "")
            
            api_version = "2024-08-01-preview" if model == "gpt-4.1" else "2024-02-15-preview"
            deployment_name = "azure-gpt-5-mini" if model == "gpt-5" else ("azure-gpt-4.1" if model == "gpt-4.1" else "azure-gpt-o3-mini")
            logger.info(f"[Keywords] Using Azure model: {deployment_name}")
            return AzureOpenAILlamaIndexLLM(
                deployment_name=deployment_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                api_base=api_base,
                api_version=api_version,
            )
        elif model == "llama3_3-70b":
            logger.info("[Keywords] Using Ollama model: llama3.3:70b (requested 'llama3_3-70b')")
            api_base = kwargs.get("api_base", None) or os.getenv("WARHOL_OLLAMA_API_BASE", "")
            return OllamaLlamaIndexLLM(
                model="llama3.3:70b",
                api_base=api_base,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise ValueError(f"Unsupported LLM model: {model}")
    
    @staticmethod
    def __chunk_to_node_with_score(
            retrieved_chunks: List[WeaviateSearchChunkResult], compared_property,
    ) -> List[NodeWithScore]:
        nodes = []
        for chunk in retrieved_chunks:
            text = chunk.retrieved_chunk[compared_property]
            if text:
                node = TextNode(text=str(text))
                node_with_score = NodeWithScore(node=node)
                nodes.append(node_with_score)
        return nodes
    
    def _llm_rerank(
            self,
            model: str,
            query: str,
            retrieved_chunks: List[WeaviateSearchChunkResult],
            compared_property="text",
            api_key=None,
            api_base=None,
            **kwargs,
    ) -> List[WeaviateSearchChunkResult]:
        """Reason provided by LLM is NOT attached, too much effort
        """
        logger.info(f"[Rerank] Starting LLM-based reranking with model: {model}")
        logger.debug(f"[Rerank] Query: {query}")
        logger.debug(f"[Rerank] Retrieved {len(retrieved_chunks)} chunks before reranking.")
        if not retrieved_chunks:
            return []
        
        # STEP 1: Select LLM
        model = cast(Literal["gpt-5", "gpt-4.1", "o3", "llama3_3-70b"], model)
        llm = self._select_llm(
            model=model, api_key=api_key, api_base=api_base, **kwargs,
        )
        
        # STEP 2: Prepare reranker
        top_n = len(retrieved_chunks)
        reranker = LLMRerank(llm=llm, top_n=top_n)
        
        # STEP 3: Convert chunks → NodeWithScore[TextNode]
        nodes = self.__chunk_to_node_with_score(retrieved_chunks, compared_property)
        
        # STEP 4: Rerank
        logger.info(f"[Rerank] Calling LLMRerank on {len(nodes)} nodes.")
        reranked_nodes = reranker.postprocess_nodes(nodes, query_bundle=QueryBundle(query_str=query))
        
        # STEP 5: Map back to chunk results with normalized scores
        reranked_scores = {node.node.text: node.score or 0.0 for node in reranked_nodes}
        
        all_chunks = []
        for chunk in retrieved_chunks:
            text = chunk.retrieved_chunk[compared_property]
            logger_text = text[:100].replace("\n", " ")
            score = reranked_scores.get(text, 0.0)
            if score == 0.0:
                norm_score = 0.0
                logger.debug(
                    f"[Rerank] No reranked score found for chunk, assigning 0.0 | Snippet: {logger_text}...",
                )
            else:
                norm_score = min(1.0, max(0.0, ((score or 1.0) - 1.0) / 9.0))
                logger.debug(
                    f"[Rerank] Reranked score for chunk: {score} -> normalized to {norm_score} | "
                    f"Snippet: {logger_text}...",
                )
            chunk.rerank_score = norm_score
            all_chunks.append(chunk)
        
        all_chunks.sort(key=lambda c: c.rerank_score, reverse=True)
        return all_chunks
    
    @staticmethod
    def _property_based_rerank(
            retrieved_chunks: List[WeaviateSearchChunkResult], forward_score: bool = False, forwarded_property: Optional[str] = None,
            reverse_order: bool = True, **kwargs,
    ) -> List[WeaviateSearchChunkResult]:
        if forward_score and forwarded_property is None:
            logger.info("[Rerank] PropertyForward: forwarding original `score` ordering")
            retrieved_chunks.sort(key=lambda c: c.score, reverse=True)
            for i, retrieved_chunk in enumerate(retrieved_chunks):
                current_score = retrieved_chunk.score
                retrieved_chunk.rerank_score = current_score
            return retrieved_chunks
        
        elif not forward_score and forwarded_property is not None:
            logger.info(
                f"[Rerank] PropertyForward: sorting by property `{forwarded_property}` (reverse={reverse_order})",
            )
            retrieved_chunks.sort(key=lambda c: c.retrieved_chunk[forwarded_property], reverse=reverse_order)
            for i, retrieved_chunk in enumerate(retrieved_chunks):
                current_value = retrieved_chunk.retrieved_chunk[forwarded_property]
                retrieved_chunk.rerank_score = current_value
            return retrieved_chunks
        
        else:
            raise ValueError("Either forward_score or forwarded_property (not both!!) must be set.")
    
    @staticmethod
    def _weighted_sum_rerank(
            scored_chunks_with_weights: List[Tuple[List[WeaviateSearchChunkResult], float]], **kwargs,
    ) -> List[WeaviateSearchChunkResult]:
        assert sum(weight for _, weight in scored_chunks_with_weights) == 1.0, "Weights must sum up to 1.0!"
        all_chunks = {}
        
        def _hash_dict(input_dict):
            return hash(tuple(sorted(input_dict.items())))
        
        logger.info(f"[Rerank] WeightedSum with {len(scored_chunks_with_weights)} inputs")
        for scored_chunks, weight in scored_chunks_with_weights:
            for scored_chunk in scored_chunks:
                hashed_reference_object = _hash_dict(scored_chunk.retrieved_chunk)
                if all_chunks.get(hashed_reference_object, None) is None:
                    all_chunks[hashed_reference_object] = WeaviateSearchChunkResult(
                        retrieved_chunk=scored_chunk.retrieved_chunk,
                        score=0.0,
                        rerank_score=0.0,
                    )
                
                all_chunks[hashed_reference_object].rerank_score = (
                        all_chunks[hashed_reference_object].rerank_score + weight * scored_chunk.rerank_score
                )
        
        all_scored_chunks = list(all_chunks.values())
        all_scored_chunks.sort(key=lambda c: c.rerank_score, reverse=True)
        
        return all_scored_chunks
    
    def _concatenated_score_rerank(
            self, query: str, retrieved_chunks: List[WeaviateSearchChunkResult], reranker_properties: List[dict], **kwargs,
    ) -> List[WeaviateSearchChunkResult]:
        def _hash_dict(input_dict):
            return hash(tuple(sorted(input_dict.items())))
        
        chunks_with_key = {
            _hash_dict(r_chunk.retrieved_chunk): WeaviateSearchChunkResult(
                retrieved_chunk=r_chunk.retrieved_chunk,
                score=r_chunk.score,
                rerank_score=0.0,
            )
            for r_chunk in retrieved_chunks
        }
        
        logger.info(f"[Rerank] Concatenate with {len(reranker_properties)} stages")
        for idx, reranker_property in enumerate(reranker_properties, start=1):
            logger.debug(f"[Rerank] Concatenate stage {idx}: {reranker_property.get('reranking_option')}")
            reranked_chunks = self.rerank(
                **reranker_property, query=query, retrieved_chunks=retrieved_chunks,
            )
            for reranked_chunk in reranked_chunks:
                chunks_with_key[_hash_dict(reranked_chunk.retrieved_chunk)].rerank_score += (reranked_chunk.rerank_score)
        
        all_scored_chunks = list(chunks_with_key.values())
        all_scored_chunks.sort(key=lambda c: c.rerank_score, reverse=True)
        return all_scored_chunks
    
    def _embedding_rerank(
            self,
            query: str,
            retrieved_chunks: List[WeaviateSearchChunkResult],
            embedder="text-embedding-3-large",
            embedded_property="text",
            **kwargs,
    ) -> List[WeaviateSearchChunkResult]:
        # STEP 1: Create embedding
        logger.info(f"[Rerank] Starting embedding-based reranking with embedder: {embedder}")
        embeddings = self.vectorizer_service.vectorize(
            texts=[query] + [r.retrieved_chunk[embedded_property] for r in retrieved_chunks],
            provider=embedder,
        )
        
        # STEP 2: Calculate scores
        query_embedding = np.array(embeddings[0])
        reranked_chunks = []
        for i, chunk in enumerate(retrieved_chunks, start=1):
            chunk_embedding = np.array(embeddings[i])
            cos_dist = float(cosine(query_embedding, chunk_embedding))
            cosine_similarity = 1 - 0.5 * cos_dist
            reranked_chunks.append(
                WeaviateSearchChunkResult(
                    retrieved_chunk=chunk.retrieved_chunk,
                    score=chunk.score,
                    rerank_score=cosine_similarity,
                ),
            )
        
        # STEP 3: Reorder
        reranked_chunks.sort(key=lambda c: c.rerank_score, reverse=True)
        return reranked_chunks
    
    def _cross_encoding_rerank(
            self,
            query: str,
            retrieved_chunks: List[WeaviateSearchChunkResult],
            cross_encoder="cross-encoder/ms-marco-MiniLM-L-6-v2",
            compared_property="text",
            **kwargs,
    ):
        """
        Cross encoder -> uses a model that directly calculates relevance score based on (query, document) input

        Options for the cross_encoder:
        - cross-encoder/ms-marco-MiniLM-L-6-v2
        - cross-encoder/ms-marco-MiniLM-L-12-v2
        - cross-encoder/stsb-roberta-base
        - BAAI/bge-reranker-base
        - BAAI/bge-reranker-large
        """
        # Step "0": define the ranges:
        # noinspection PyPep8Naming
        MODEL_SCORE_RANGES = {
            "cross-encoder/ms-marco-MiniLM-L-6-v2": (-10.0, 10.0),  # https://sbert.net/docs/cross_encoder/pretrained_models.html
            "cross-encoder/ms-marco-MiniLM-L-12-v2": (-10.0, 10.0),
            "BAAI/bge-reranker-base": (0.0, 1.0),
            "BAAI/bge-reranker-large": (0.0, 1.0),  # suited for Chinese / english
            "BAAI/bge-reranker-v2-m3": (0.0, 1.0),  # good option for multilingual
            "BAAI/bge-reranker-v2-gemma": (0.0, 1.0),
            "cross-encoder/stsb-roberta-base": (0.0, 1.0),  # similar to base of bge-reranker-large
        }
        min_score, max_score = MODEL_SCORE_RANGES[cross_encoder]
        score_range = max(max_score - min_score, 1e-6)
        
        # Step 1: Convert chunks into nodes
        if not query:
            all_chunks = []
            for chunk in retrieved_chunks:
                text = chunk.retrieved_chunk[compared_property]
                logger_text = text[:100].replace("\n", " ")
                score = 0.0
                logger.debug(
                    f"[Rerank] NO QUERY Score: {score:.4f} | Snippet: {logger_text}...",
                )
                all_chunks.append(
                    WeaviateSearchChunkResult(
                        retrieved_chunk=chunk.retrieved_chunk,
                        score=chunk.score,
                        rerank_score=score,
                    ),
                )
            
            return all_chunks
        
        nodes = self.__chunk_to_node_with_score(retrieved_chunks, compared_property)
        
        # Step 2: Use the CrossEncoder model
        logger.info(f"[Rerank] CrossEncoder model={cross_encoder} | nodes={len(nodes)}")
        reranked = SentenceTransformerRerank(model=cross_encoder, top_n=len(nodes))
        
        # Step 3: Run reranking
        reranked_nodes = reranked.postprocess_nodes(nodes, query_bundle=QueryBundle(query_str=query))
        
        # Step 4: Map scores back to chunks (normalize to [0, 1] based on range)
        reranked_scores = {node.node.text: node.score for node in reranked_nodes}
        
        all_chunks = []
        for chunk in retrieved_chunks:
            text = chunk.retrieved_chunk[compared_property]
            logger_text = text[:100].replace("\n", " ")
            score = float(reranked_scores.get(text, 0.0))
            norm_score = max(0.0, min(1.0, (score - min_score) / score_range))
            logger.debug(
                f"[Rerank] Score: {score:.4f} -> normalized to {norm_score:.4f} | Snippet: {logger_text}...",
            )
            all_chunks.append(
                WeaviateSearchChunkResult(
                    retrieved_chunk=chunk.retrieved_chunk,
                    score=chunk.score,
                    rerank_score=norm_score,
                ),
            )
        
        all_chunks.sort(key=lambda c: c.rerank_score, reverse=True)
        return all_chunks
    
    def _tilde_rerank(
            self, query: str, retrieved_chunks: List[WeaviateSearchChunkResult], compared_property="text", translate: bool = False,
            translate_model: str = "", **kwargs,
    ):
        """
        Idea: see this paper: https://arxiv.org/abs/2108.08513
        """
        logger.debug(f"[Rerank] TILDE query: {query[:15]}... | translate={translate} | model={translate_model or '-'}")
        
        # Step 1: Convert chunks into nodes
        nodes = self.__chunk_to_node_with_score(retrieved_chunks, compared_property)
        
        # Step 2: Optionally, add a translator
        llm = None
        if translate:
            if translate_model in ("gpt-4.1", "o3"):
                api_version = "2024-08-01-preview" if translate_model == "gpt-4.1" else "2024-02-15-preview"
                deployment_name = "azure-gpt-5-mini" if translate_model == "gpt-5" else (
                    "azure-gpt-4.1" if translate_model == "gpt-4.1" else "azure-gpt-o3-mini")
                llm = AzureOpenAILlamaIndexLLM(
                    deployment_name=deployment_name,
                    temperature=0.0,  # deterministic translation
                    api_key=kwargs.get("api_key", None) or os.getenv("AZURE_OPENAI_API_KEY", ""),
                    api_base=kwargs.get("api_base", None) or os.getenv("AZURE_OPENAI_API_BASE", ""),
                    api_version=api_version,
                )
                logger.info(f"[Rerank] Using Azure model for translation: {deployment_name}")
            elif translate_model == "llama3_3-70b":
                api_base = kwargs.get("api_base", None) or os.getenv("WARHOL_OLLAMA_API_BASE", "")
                llm = OllamaLlamaIndexLLM(
                    model="llama3.3:70b",
                    api_base=api_base,
                    temperature=0.0,
                )
                logger.info("[Rerank] Using Ollama model for translation: llama3.3:70b")
            else:
                raise ValueError(f"Unsupported translation model {translate_model}")
        
        # Step 3: Choose and configure TILDE reranker
        reranker = TILDEv2Reranker(**kwargs)
        
        # Step 4: Optionally, translate + Run reranking
        if translate and llm is not None:
            prompt = lambda text: (
                "Translate the following German text to English. "
                "Return only the translation with no extra commentary:\n\n"
                f"{text.strip()}"
            )
            # translate query
            query_en = llm.complete(prompt(query)).text.strip()
            logger.debug(f"[Rerank] Translated query: {query_en[:15]}...")
            
            # translate each node’s text
            translated_nodes = []
            for node in nodes:
                orig = node.node.text
                translated = llm.complete(prompt(orig)).text.strip()
                node = TextNode(text=translated)
                node_with_score = NodeWithScore(node=node)
                translated_nodes.append(node_with_score)
                logger.debug(f"[Rerank] Translated passage: {translated[:15]}...")
            nodes = translated_nodes
        else:
            query_en = query
        
        reranked_nodes = reranker.postprocess_nodes(
            nodes, query_bundle=QueryBundle(query_str=query_en),
        )
        
        logger.debug(f"[Rerank] TILDE produced {len(reranked_nodes)} nodes with scores")
        # Step 4: Map scores back to chunks
        reranked_scores = {hash(node.node.text): node.score for node in reranked_nodes}
        
        all_chunks = []
        for chunk in retrieved_chunks:
            text = chunk.retrieved_chunk[compared_property]
            logger_text = text[:100].replace("\n", " ")
            score = float(reranked_scores.get(hash(text), 0.0))
            norm_score = reranker.normalize_score(score)  # sigmoid
            logger.debug(
                f"[Rerank] Score: {score:.4f} -> normalized to {norm_score:.4f} | Snippet: {logger_text}...",
            )
            all_chunks.append(
                WeaviateSearchChunkResult(
                    retrieved_chunk=chunk.retrieved_chunk,
                    score=chunk.score,
                    rerank_score=norm_score,
                ),
            )
        
        all_chunks.sort(key=lambda c: c.rerank_score, reverse=True)
        return all_chunks
