from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components import render_template
from app.services.system.components.post_processor.chunk_filter.abstract_chunk_filter import ChunkFilterProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TopNChunkFilter(ChunkFilterProcessor, variant_name="top_n"):
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.top_n_template = self.parameters.get("top_n", None)
        self.threshold_template = self.parameters.get("threshold", None)
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "top_n": {
                    "type": "int",
                    "description": "Optional (but either this or threshold must be set): can filter for top n chunks (according to rerank score)",
                    "default": "BAAI/bge-reranker-v2-gemma",
                },
                "threshold": {
                    "type": "float",
                    "description": "Property of retrieved chunk which to compare to query",
                    "default": "text",
                },
            },
        )
        return base_params
    
    def process(self, query: str, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        if isinstance(self.top_n_template, str):
            top_n = render_template(self.top_n_template, data)
        else:
            top_n = self.top_n_template
        if isinstance(self.threshold_template, str):
            threshold_template = render_template(self.threshold_template, data)
        else:
            threshold_template = self.threshold_template
        
        if top_n is None and threshold_template is None:
            raise ValueError("TopNChunkFilter: At least top_n or threshold must be set.")
        
        return self.advanced_vector_service.filter_top_n_and_threshold(
            retrieved_chunks=retrievals,
            top_n=top_n,
            threshold=threshold_template,
        )
