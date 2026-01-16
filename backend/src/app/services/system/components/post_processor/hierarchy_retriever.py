from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.knowledge.vector import HierarchicalIndexVectorDBService
from app.services.system.components import render_template
from app.services.system.components.post_processor.abstract_post_processor import AbstractPostProcessor
from app.utils.logger import setup_logger
from app.utils.service_creators import get_hierarchical_vector_service

logger = setup_logger(__name__)


class HierarchyRetriever(AbstractPostProcessor, variant_name="hierarchy_retrieval"):
    default_parameters: Dict[str, Any] = {
        **AbstractPostProcessor.default_parameters,
        "include_whole_parent_threshold": 0.6,
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.hierarchy_vector_service: HierarchicalIndexVectorDBService = get_hierarchical_vector_service()
        
        self.include_whole_parent_threshold_temp = self.parameters.get("include_whole_parent_threshold") or self.default_parameters[
            "include_whole_parent_threshold"
        ]
        self.weaviate_collection = self.parameters.get("weaviate_collection")
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "weaviate_collection": {
                    "type": "string",
                    "description": "Weaviate collection to use for the retrieval (will send query, top_k)",
                },
                "include_whole_parent_threshold": {
                    "type": "float",
                    "description": "The threshold determining at what ratio (included leaves) an entire parent branch should be included",
                },
            },
        )
        return base_params
    
    def process(self, _, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        include_whole_parent_threshold = render_template(self.include_whole_parent_threshold_temp, data)
        final_retrieval = self.hierarchy_vector_service.retrieve_automerge(
            collection_name=self.weaviate_collection,
            retrieval_start=retrievals,
            simple_ratio_threshold=include_whole_parent_threshold,
        )
        
        logger.debug(
            f"[HierarchyRetriever] Retrieved {len(final_retrieval)} unique chunks (added {len(final_retrieval) - len(retrievals)} by adding parents)",
        )
        return final_retrieval
