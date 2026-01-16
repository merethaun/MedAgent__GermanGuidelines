from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components.post_processor.chunk_order.abstract_chunk_order import ChunkOrderProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class CrossEncoderChunkOrder(ChunkOrderProcessor, variant_name="cross_encoding"):
    default_parameters: Dict[str, Any] = {
        **ChunkOrderProcessor.default_parameters,
        "compared_property": "text",
        "cross_encoder": "BAAI/bge-reranker-v2-gemma",
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.reranking_option = "cross_encoding"
        self.cross_encoder = self.parameters.get("cross_encoder") or self.default_parameters["cross_encoder"]
        self.compared_property = self.parameters.get("compared_property") or self.default_parameters["compared_property"]
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "cross_encoder": {
                    "type": "str",
                    "description": "Cross encoding model used create scores, "
                                   "options: [cross-encoder/ms-marco-MiniLM-L-6-v2, cross-encoder/ms-marco-MiniLM-L-12-v2, "
                                   "BAAI/bge-reranker-base, BAAI/bge-reranker-large, BAAI/bge-reranker-v2-m3, BAAI/bge-reranker-v2-gemma, "
                                   "cross-encoder/stsb-roberta-base",
                    "default": "BAAI/bge-reranker-v2-gemma",
                },
                "compared_property": {
                    "type": "string",
                    "description": "Property of retrieved chunk which to compare to query",
                    "default": "text",
                },
            },
        )
        return base_params
    
    def process(self, query: str, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        return self.advanced_vector_service.rerank(
            reranking_option=self.reranking_option,
            query=query,
            retrieved_chunks=retrievals,
            cross_encoder=self.cross_encoder,
            compared_property=self.compared_property,
        )
