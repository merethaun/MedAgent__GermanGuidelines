from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components.post_processor.chunk_order.abstract_chunk_order import ChunkOrderProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class EmbeddingChunkOrder(ChunkOrderProcessor, variant_name="embedding"):
    default_parameters: Dict[str, Any] = {
        **ChunkOrderProcessor.default_parameters,
        "embedded_property": "text",
        "embedder": "text-embedding-3-large",
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.reranking_option = "embedding"
        self.embedder = self.parameters.get("embedder") or self.default_parameters["embedder"]
        self.embedded_property = self.parameters.get("embedded_property") or self.default_parameters["embedded_property"]
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "embedder": {
                    "type": "str",
                    "description": "Embedding model used create vectors -> then applied to cosine similarity",
                    "default": "text-embedding-3-large",
                },
                "embedded_property": {
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
            embedder=self.embedder,
            embedded_property=self.embedded_property,
        )
