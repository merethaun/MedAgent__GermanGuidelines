from abc import abstractmethod
from typing import Dict, Type, Any, Optional, Tuple

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AbstractRetriever(AbstractComponent, variant_name="retriever"):
    variants: Dict[str, Type['AbstractRetriever']] = {}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.next_component_id = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractRetriever.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        # TODO: add history of previous retrieval??
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "query": {
                "type": "string",
                "description": "Term based on which the 'most relevant' entries are extracted (will be resolved with the variables specified)",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "retriever.query": {
                "type": "string", "description": "The query used for retrieval, available under namespace of component",
            },
            "retriever.results": {
                "type": "list", "description": "List of retrieved objects with retrieval scores",
            },
        }
    
    @abstractmethod
    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[list, float]:
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            logger.info(f"[Retriever] Starting execution for {self.__class__.__name__} (ID: {self.id})")
            query_template = self.parameters["query"]
            query = render_template(query_template, data)
            
            logger.info(f"[Retriever] Query: {query}")
            data[f"{self.id}.query"] = query
            if query.strip():
                results, latency = self.retrieve(query=query, data=data)
            else:
                results, latency = [], 0.0
            logger.info(f"[Retriever] Retrieved {len(results) if results else 0} results in {latency:.2f} s")
            
            data[f"{self.id}.results"] = results
            data[f"{self.id}.latency"] = latency
            logger.info(f"[Retriever] Execution completed successfully")
            return data, self.next_component_id
        
        except Exception as e:
            logger.exception(f"[Retriever] Failed to retrieve for {self.__class__.__name__} (ID: {self.id}):")
            logger.error(f"[Retriever] Error details: {str(e)}")
            raise RuntimeError(f"Retriever execution failed: {e}")
