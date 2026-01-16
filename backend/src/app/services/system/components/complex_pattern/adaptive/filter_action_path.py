from typing import Dict, Any, Tuple, List

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.knowledge.vector import AdvancedDBService
from app.services.system.components import AbstractComponent, render_template
from app.services.system.components.post_processor.chunk_filter.relevance_in_generation_filter import LLMRelevanceFilter
from app.utils.logger import setup_logger
from app.utils.service_creators import get_advanced_db_service

logger = setup_logger(__name__)


class FilterActionComponent(AbstractComponent, variant_name="filter_action_path"):
    default_parameters: Dict[str, Any] = {
        "query_threshold": 0.65,
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        
        self.next_component_id = None
        
        self.retrievals_temp = parameters["retrievals"]
        self.filter_option_temp = parameters["filter_option"]
        self.query_temp = parameters["query"]
        self.query_threshold_temp = parameters.get("query_threshold") or self.default_parameters["query_threshold"]
        self.current_generation_result_temp = parameters["current_generation_result"]
        
        self.advanced_vector_service: AdvancedDBService = get_advanced_db_service()
        self.generation_based_llm_filter = LLMRelevanceFilter("gpt-4.1", None, None)
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "retrievals": {
                "type": "str",
                "description": "Template for how to get to retrievals.",
            },
            "filter_option": {
                "type": "str",
                "description": "Template for how to get to filter option (query or generation_based).",
            },
            "query": {
                "type": "str",
                "description": "Template for query to base filter on -> IF query.",
            },
            "query_threshold": {
                "type": "float",
                "description": "Template for threshold to base filter on (filter <= threshold) -> IF query.",
            },
            "current_generation_result": {
                "type": "str",
                "description": "Template for how to get current generation result to base filter on -> IF generation_based.",
            },
        }
    
    def rerank_and_filter(self, query: str, retrievals, relevance_filter: float = 0.4):
        ordered_retrievals = self.advanced_vector_service.rerank(
            query=query,
            retrieved_chunks=retrievals,
            reranking_option="llm",
            compared_property="text",
            model="gpt-4.1",
        )
        logger.debug(f"Reranked results")
        
        filtered_retrieval = self.advanced_vector_service.filter_top_n_and_threshold(
            retrieved_chunks=ordered_retrievals,
            threshold=relevance_filter,
        )
        logger.debug(f"Filtered results to {len(filtered_retrieval)} results (remove {len(ordered_retrievals) - len(filtered_retrieval)})")
        return filtered_retrieval
    
    def filter_generation_based(self, retrievals, generation_result: str):
        filtered_retrieval = self.generation_based_llm_filter.filter_retrievals(generation_result, retrievals, "text")
        logger.debug(f"Filtered results to {len(filtered_retrieval)} results (remove {len(retrievals) - len(filtered_retrieval)})")
        return filtered_retrieval
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        current_retrieval = render_template(self.retrievals_temp, data)
        filter_option = render_template(self.filter_option_temp, data)
        
        if filter_option == "query":
            query = render_template(self.query_temp, data)
            if not query:
                raise ValueError("Query is empty -> but required for query filter")
            
            query_threshold = render_template(self.query_threshold_temp, data)
            final_retrieval = self.rerank_and_filter(query, current_retrieval, query_threshold)
        elif filter_option == "generation_based":
            current_generation_result = render_template(self.current_generation_result_temp, data)
            if not current_generation_result:
                raise ValueError("Generation result is empty -> but required for generation_based filter")
            
            final_retrieval = self.filter_generation_based(current_retrieval, current_generation_result)
        else:
            raise ValueError(f"Unknown filter option: {filter_option}")
        
        logger.debug(f"Final retrieval size: {len(final_retrieval)} (removed {len(current_retrieval) - len(final_retrieval)} chunks)")
        data[f"{self.id}.retrievals"] = final_retrieval
        
        return data, self.next_component_id
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "filter_action_path.retrievals": {
                "type": List[WeaviateSearchChunkResult],
                "description": "Tracks the action with their settings + results (in form of scores) -> can track progress",
            },
        }
