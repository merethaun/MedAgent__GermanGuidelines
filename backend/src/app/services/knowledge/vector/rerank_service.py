import time
from typing import List, Dict

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchResult, WeaviateSearchChunkResult
from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)


class RerankService:
    
    @staticmethod
    def rerank_and_filter(items: List[Dict], top_k: int) -> WeaviateSearchResult:
        start = time.time()
        
        chunks_with_scores = {}
        max_relevance_factor = sum([item["weight"] for item in items])
        for item in items:
            retrieved_chunk: dict = item["retrieved_chunk"]
            retrieval_score: float = item["score"]
            item_weight: float = item["weight"]
            prefix: str = item["prefix"]
            
            item_key = f"{prefix}_{retrieved_chunk['chunk_index']}"
            normalized_relevance_factor = item_weight / max_relevance_factor
            if item_key in chunks_with_scores:
                chunks_with_scores[item_key]["score"] += normalized_relevance_factor * retrieval_score
            else:
                chunks_with_scores[item_key] = {
                    "chunk": retrieved_chunk,
                    "score": normalized_relevance_factor * retrieval_score,
                }
        
        chunks = [
            WeaviateSearchChunkResult(retrieved_chunk=result["chunk"], score=result["score"])
            for _, result in chunks_with_scores.items()
        ]
        chunks.sort(key=lambda r: r.score, reverse=True)
        results = chunks[:top_k]
        
        end = time.time()
        duration = end - start
        logger.debug(f"Rerank with vector similarity took {duration} seconds with updated results: {results}")
        logger.info(f"Reranking completed in {duration:.2f}s with {len(results)} results")
        return WeaviateSearchResult(results=results, duration=duration)
