from abc import abstractmethod
from typing import Dict, Type, Any, Optional, Tuple

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AbstractJudge(AbstractComponent, variant_name="judge"):
    variants: Dict[str, Type['AbstractJudge']] = {}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
        
        self.query_template = self.parameters.get("query", None)
        self.current_retrieval_template = self.parameters.get("current_retrieval", None)
        self.current_response_template = self.parameters.get("current_response", None)
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractJudge.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "query": {
                    "type": "string",
                    "description": "The question to be split into subproblems",
                },
                "current_retrieval": {
                    "type": "list",
                    "description": "List of current context (ideally, include as list of strings, similar to as generator would receive)",
                    "default": [],
                },
                "current_response": {
                    "type": "string",
                    "description": "Current response",
                    "default": "",
                },
            },
        )
        return base_params
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "judge.query": {
                "type": "string",
                "description": "Rendered input query to evaluate",
            },
            "judge.current_retrieval": {
                "type": "string",
                "description": "Rendered input retrieval to evaluate",
            },
            "judge.current_response": {
                "type": "string",
                "description": "Rendered input response to evaluate",
            },
        }
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        # TODO: add history of previous processing??
        pass
    
    @abstractmethod
    def judge(self, query, current_retrieval, current_response, data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        query = render_template(self.query_template, data)
        current_retrieval = render_template(self.current_retrieval_template, data)
        current_response = render_template(self.current_response_template, data)
        
        data[f"{self.id}.query"] = query
        data[f"{self.id}.current_retrieval"] = current_retrieval
        data[f"{self.id}.current_response"] = current_response
        
        return self.judge(query, current_retrieval, current_response, data), self.next_component_id
