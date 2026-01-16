from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components.post_processor.chunk_order.abstract_chunk_order import ChunkOrderProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class PropertyForwardChunkOrder(ChunkOrderProcessor, variant_name="property_forward"):
    """
    Simple property/score forwarding & sorting:
      - If forward_score=True -> forward the original `score` as `rerank_score` (ranked).
      - Else -> sort by `forwarded_property` taken from each retrieved chunk.
    """
    default_parameters: Dict[str, Any] = {
        **ChunkOrderProcessor.default_parameters,
        "forward_score": True,  # mutually exclusive with forwarded_property
        "forwarded_property": None,  # e.g. "publishedAt" or any field in retrieved_chunk
        "reverse_order": True,  # True => descending (1, 0.9, ...)
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.reranking_option = "property_forward"
        
        self.forward_score = bool(self.parameters.get("forward_score", self.default_parameters["forward_score"]))
        self.forwarded_property = self.parameters.get("forwarded_property", self.default_parameters["forwarded_property"])
        self.reverse_order = bool(self.parameters.get("reverse_order", self.default_parameters["reverse_order"]))
        
        if self.forward_score and self.forwarded_property:
            raise ValueError("PropertyForwardChunkOrder: Choose either forward_score=True OR set forwarded_property, not both.")
        
        if not self.forward_score and not self.forwarded_property:
            raise ValueError("PropertyForwardChunkOrder: Either forward_score must be True OR forwarded_property must be set.")
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "forward_score": {
                    "type": "bool",
                    "description": "Forward the original retrieval `score` as rank (descending). Mutually exclusive with forwarded_property.",
                    "default": True,
                },
                "forwarded_property": {
                    "type": "string",
                    "description": "If set, sort by this property from each retrieved chunk (mutually exclusive with forward_score).",
                },
                "reverse_order": {
                    "type": "bool",
                    "description": "Whether to sort in descending (large to small, True) or ascending (False) order when using forwarded_property.",
                    "default": True,
                },
            },
        )
        return base
    
    def process(self, query: str, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        return self.advanced_vector_service.rerank(
            reranking_option=self.reranking_option,
            retrieved_chunks=retrievals,
            forward_score=self.forward_score,
            forwarded_property=self.forwarded_property,
            reverse_order=self.reverse_order,
        )
