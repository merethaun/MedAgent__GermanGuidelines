from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components.post_processor.chunk_order.abstract_chunk_order import ChunkOrderProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConcatenateChunkOrder(ChunkOrderProcessor, variant_name="concatenate"):
    """
    Concatenates scores from multiple rerankers into a tuple and sorts lexicographically (descending).

    Parameters:
      - reranker_properties: List[dict] (no weights)
            Each dict should contain 'reranking_option' and params for that reranker.
      - api_key/api_base: forwarded to sub-rerankers if not present in that sub-config.
    """
    default_parameters: Dict[str, Any] = {
        **ChunkOrderProcessor.default_parameters,
        "reranker_properties": [
            # sensible default chain
            {"reranking_option": "embedding", "embedded_property": "text", "embedder": "text-embedding-3-large"},
            {"reranking_option": "property_forward", "forward_score": True},
        ],
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.reranking_option = "concatenate"
        self.reranker_properties: List[Dict[str, Any]] = self.parameters.get("reranker_properties") or self.default_parameters["reranker_properties"]
        
        if not isinstance(self.reranker_properties, list) or len(self.reranker_properties) == 0:
            raise ValueError("ConcatenateChunkOrder: `reranker_properties` must be a non-empty list.")
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "reranker_properties": {
                    "type": "list[dict]",
                    "description": (
                        "List of sub-rerankers to concatenate (no weights). Example:\n"
                        "[\n"
                        "  {\"reranking_option\": \"embedding\", \"embedded_property\": \"text\", \"embedder\": \"text-embedding-3-large\"},\n"
                        "  {\"reranking_option\": \"cross_encoding\", \"cross_encoder\": \"BAAI/bge-reranker-base\", \"compared_property\": \"text\"}\n"
                        "]"
                    ),
                    "default": [
                        {"reranking_option": "embedding", "embedded_property": "text", "embedder": "text-embedding-3-large"},
                        {"reranking_option": "property_forward", "forward_score": True},
                    ],
                },
            },
        )
        return base
    
    def process(self, query: str, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        sub_props: List[Dict[str, Any]] = []
        for rp in self.reranker_properties:
            cfg = dict(rp)
            sub_props.append(cfg)
        
        return self.advanced_vector_service.rerank(
            reranking_option=self.reranking_option,
            query=query,
            retrieved_chunks=retrievals,
            reranker_properties=sub_props,
        )
