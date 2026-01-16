from abc import abstractmethod
from typing import Dict, Type, Any, Optional, Tuple, List

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AbstractPostProcessor(AbstractComponent, variant_name="post_process"):
    variants: Dict[str, Type['AbstractPostProcessor']] = {}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractPostProcessor.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        # TODO: add history of previous processing??
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "query": {
                "type": "string",
                "description": "Default: none; Typically input of user (retrievals where based on)",
            },
            "retrievals": {
                "type": "string",
                "description": "Raw retrieval results",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "post_process.query": {
                "type": "string", "description": "The query used for retrieval, available under namespace of component",
            },
            "post_process.retrievals": {
                "type": "list", "description": "List of retrieved objects with retrieval scores",
            },
            "post_process.updated_retrievals": {
                "type": "list", "description": "The post processed retrieval scores",
            },
        }
    
    @abstractmethod
    def process(self, query: str, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            logger.info(f"[PostProcessor] Starting execution for {self.__class__.__name__} (ID: {self.id})")
            query_template = self.parameters.get("query", None)
            query = render_template(query_template, data) if query_template else ""
            
            logger.info(f"[PostProcessor] Query: {query}")
            data[f"{self.id}.query"] = query
            
            retrieval_template = self.parameters["retrievals"]
            logger.debug(f"[PostProcessor] Retrieval template: {retrieval_template}")
            if isinstance(retrieval_template, str):
                retrieval = render_template(retrieval_template, data)
            else:
                retrieval = retrieval_template
            
            logger.debug(f"[PostProcessor] Retrieval template: {retrieval}")
            
            for i, retrieval_item in enumerate(retrieval):
                if isinstance(retrieval_item, WeaviateSearchChunkResult):
                    continue
                else:
                    retrieval[i] = WeaviateSearchChunkResult(
                        retrieved_chunk=retrieval_item["retrieved_chunk"],
                        score=retrieval_item.get("score", 0.0),
                        rerank_score=retrieval_item.get("rerank_score", None),
                    )
            
            logger.info(f"[PostProcessor] Processing {len(retrieval)} retrievals")
            # data[f"{self.id}.retrievals"] = retrieval
            
            processed_retrievals = self.process(query, retrieval, data)
            data[f"{self.id}.updated_retrievals"] = processed_retrievals
            
            logger.info(f"[PostProcessor] Execution completed successfully")
            return data, self.next_component_id
        
        except Exception as e:
            logger.exception(f"[PostProcessor] Failed to postprocess for {self.__class__.__name__} (ID: {self.id}):")
            logger.error(f"[PostProcessor] Error details: {str(e)}", exc_info=True)
            raise RuntimeError(f"PostProcessor execution failed: {e}")
