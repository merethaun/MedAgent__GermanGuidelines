from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components import render_template
from app.services.system.components.post_processor.chunk_filter.abstract_chunk_filter import ChunkFilterProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class DeduplicateChunkFilter(ChunkFilterProcessor, variant_name="deduplicate"):
    """
    Greedy duplicate filter that keeps the first occurrence and removes near-duplicates
    using the selected 'rank_method' via AdvancedDBService.filter_duplicates(...).
    """
    
    default_parameters: Dict[str, Any] = {
        **ChunkFilterProcessor.default_parameters,
        # generic
        "keep_all_guidelines": True,
        "compared_property": "text",
        "rank_method": "cross_encoding",  # {"embedding","cross_encoding","llm"}
        "similarity_threshold": 0.95,  # passed as cutoff_similarity to the service
        # embedding method
        "embedder": "text-embedding-3-large",
        # cross-encoder method
        "cross_encoder": "BAAI/bge-reranker-v2-gemma",
        # llm method
        "llm_model": "gpt-4.1",
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        # store templates/raws; resolve at process-time via render_template(...)
        self.keep_all_guidelines_template = self.parameters.get("keep_all_guidelines", self.default_parameters["keep_all_guidelines"])
        self.compared_property_template = self.parameters.get("compared_property", self.default_parameters["compared_property"])
        self.rank_method_template = self.parameters.get("rank_method", self.default_parameters["rank_method"])
        self.threshold_template = self.parameters.get("similarity_threshold", self.default_parameters["similarity_threshold"])
        
        # method-specific knobs (possibly templates)
        self.embedder_template = self.parameters.get("embedder", self.default_parameters["embedder"])
        
        self.cross_encoder_template = self.parameters.get("cross_encoder", self.default_parameters["cross_encoder"])
        
        self.model_template = self.parameters.get("llm_model", self.default_parameters["llm_model"])
        self.api_key_template = self.parameters.get("llm_api_key", None)
        self.api_base_template = self.parameters.get("llm_api_base", None)
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "keep_all_guidelines": {
                    "type": "bool",
                    "description": "Deduplicate within each guideline_id (True) or across all results (False).",
                    "default": True,
                },
                "rank_method": {
                    "type": "string",
                    "description": "Similarity method for duplicate detection. Options: [embedding, cross_encoding, llm].",
                    "default": "cross_encoding",
                },
                "similarity_threshold": {
                    "type": "float",
                    "description": "Cutoff in [0,1]. If similarity >= threshold, a chunk is considered a duplicate of the kept one.",
                    "default": 0.95,
                },
                "compared_property": {
                    "type": "string",
                    "description": "Property of the retrieved chunk to compare for similarity (text field).",
                    "default": "text",
                },
                # embedding-specific
                "embedder": {
                    "type": "string",
                    "description": "Embedding model provider id used for similarity when rank_method=embedding.",
                    "default": "text-embedding-3-large",
                },
                # cross-encoder-specific
                "cross_encoder": {
                    "type": "string",
                    "description": "Cross-encoder model when rank_method=cross_encoding. "
                                   "Options e.g.: [cross-encoder/ms-marco-MiniLM-L-6-v2, cross-encoder/ms-marco-MiniLM-L-12-v2, "
                                   "BAAI/bge-reranker-base, BAAI/bge-reranker-large, BAAI/bge-reranker-v2-m3, BAAI/bge-reranker-v2-gemma, "
                                   "cross-encoder/stsb-roberta-base]",
                    "default": "BAAI/bge-reranker-v2-gemma",
                },
                # llm-specific
                "llm_model": {
                    "type": "string",
                    "description": "LLM to judge redundancy when rank_method=llm. Options: [gpt-4.1, gpt-3.5, llama3-8b].",
                    "default": "gpt-4.1",
                },
                "llm_api_key": {
                    "type": "string",
                    "description": "API key for the chosen LLM (Azure OpenAI for GPT variants).",
                    "default": "",
                },
                "llm_api_base": {
                    "type": "string",
                    "description": "API base URL for the chosen LLM (Azure endpoint for GPT variants).",
                    "default": "",
                },
            },
        )
        return base_params
    
    def process(self, query: str, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        """
        Resolve parameters (with templating), then call AdvancedDBService.filter_duplicates(...)
        """
        
        def _render(v):
            return render_template(v, data) if isinstance(v, str) else v
        
        keep_all_guidelines = bool(_render(self.keep_all_guidelines_template))
        compared_property = _render(self.compared_property_template) or self.default_parameters["compared_property"]
        rank_method = (_render(self.rank_method_template) or self.default_parameters["rank_method"]).strip()
        cutoff_similarity = float(
            _render(self.threshold_template) if self.threshold_template is not None else self.default_parameters["similarity_threshold"],
        )
        
        if rank_method not in {"embedding", "cross_encoding", "llm"}:
            raise ValueError(f"DeduplicateChunkFilter: Unsupported rank_method '{rank_method}'. Use one of: embedding, cross_encoding, llm.")
        
        # Assemble method-specific kwargs
        method_kwargs: Dict[str, Any] = {}
        if rank_method == "embedding":
            embedder = _render(self.embedder_template) or self.default_parameters["embedder"]
            method_kwargs.update({"embedder": embedder})
        elif rank_method == "cross_encoding":
            cross_encoder = _render(self.cross_encoder_template) or self.default_parameters["cross_encoder"]
            method_kwargs.update({"cross_encoder": cross_encoder})
        elif rank_method == "llm":
            model = _render(self.model_template) or self.default_parameters["llm_model"]
            api_key = _render(self.api_key_template)
            api_base = _render(self.api_base_template)
            method_kwargs.update({"llm_model": model})
            if api_key:
                method_kwargs.update({"llm_api_key": api_key})
            if api_base:
                method_kwargs.update({"llm_api_base": api_base})
        
        logger.info(
            f"[DeduplicateChunkFilter] rank_method={rank_method} cutoff={cutoff_similarity} "
            f"keep_all_guidelines={keep_all_guidelines} compared_property={compared_property}",
        )
        
        # Call the AdvancedDBService
        return self.advanced_vector_service.filter_duplicates(
            retrieved_chunks=retrievals,
            keep_all_guidelines=keep_all_guidelines,
            compared_property=compared_property,
            rank_method=rank_method,
            cutoff_similarity=cutoff_similarity,
            **method_kwargs,
        )
