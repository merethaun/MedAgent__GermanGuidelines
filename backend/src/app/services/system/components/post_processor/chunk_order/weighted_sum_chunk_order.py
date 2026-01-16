from typing import Dict, Any, List, Tuple

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components import render_template
from app.services.system.components.post_processor.chunk_order.abstract_chunk_order import ChunkOrderProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class WeightedSumChunkOrder(ChunkOrderProcessor, variant_name="weighted_sum"):
    """
    Combine multiple already-reranked chunk lists by a weighted sum of their `rerank_score`s.

    Expected runtime input (preferred):
        data["scored_chunks_with_weights"] = List[Tuple[List[WeaviateSearchChunkResult | dict], float]]
        # e.g., [
        #   ([{...chunk...}, {...}], 0.8),
        #   ([{...chunk...}, {...}], 0.2),
        # ]

    Notes:
    - Weights are validated and normalized to sum to 1.0 before calling AdvancedDBService.
    - If not present in `data`, falls back to `parameters['scored_chunks_with_weights']` (useful for tests).
    """
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.reranking_option = "weighted_sum"
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "scored_chunks_with_weights": {
                "type": "list[tuple[list[dict], float]]",
                "description": (
                    "A list of chunk-reorder results WITH weights, to calculate the weighted sum of their rerank scores."
                ),
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "post_process.scored_chunks_with_weights": {
                "type": "list", "description": "Resolved chunks with weights",
            },
            "post_process.updated_retrievals": {
                "type": "list", "description": "The post processed retrieval scores",
            },
        }
    
    def process(self, query: str, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            param_value = self.parameters.get("scored_chunks_with_weights")
            
            # transform chunks with scores
            if isinstance(param_value, str):
                resolved_chunks_with_weights = render_template(param_value, data)
            elif isinstance(param_value, list):
                resolved_chunks_with_weights = param_value
                for i, item in enumerate(resolved_chunks_with_weights):
                    if isinstance(item, str):
                        resolved_chunks_with_weights[i] = render_template(item, data)
            else:
                raise ValueError(
                    f"WeightedSumChunkOrder: `scored_chunks_with_weights` must be a string or a list of strings.",
                )
            for i, (cs, w) in enumerate(resolved_chunks_with_weights):
                resolved_chunks_with_weights[i] = (
                    [
                        WeaviateSearchChunkResult(
                            retrieved_chunk=c["retrieved_chunk"], score=c["score"], rerank_score=c["rerank_score"],
                        ) if not isinstance(c, WeaviateSearchChunkResult) else c
                        for c in cs
                    ],
                    w,
                )
            
            # normalize weights
            assert all([w >= 0 for (_, w) in resolved_chunks_with_weights])
            total = sum([w for (_, w) in resolved_chunks_with_weights])
            resolved_chunks_with_weights = [(cs, w / total) for (cs, w) in resolved_chunks_with_weights]
            
            data[f"{self.id}.scored_chunks_with_weights"] = resolved_chunks_with_weights
            
            chunks_with_combined_weights = self.advanced_vector_service.rerank(
                reranking_option=self.reranking_option,
                scored_chunks_with_weights=resolved_chunks_with_weights,
            )
            data[f"{self.id}.updated_retrievals"] = chunks_with_combined_weights
            
            return data, self.next_component_id
        except Exception as e:
            logger.exception(f"[WeightedSumChunkOrder] Failed to postprocess for {self.__class__.__name__} (ID: {self.id}):")
            logger.error(f"[WeightedSumChunkOrder] Error details: {str(e)}", exc_info=True)
            raise RuntimeError(f"WeightedSumChunkOrder execution failed: {e}")
