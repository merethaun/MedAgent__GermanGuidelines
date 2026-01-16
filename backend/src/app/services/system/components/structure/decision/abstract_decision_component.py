from abc import abstractmethod
from typing import Dict, Any, Tuple, Type, Optional

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AbstractDecisionComponent(AbstractComponent, variant_name="decision"):
    variants: Dict[str, Type['AbstractDecisionComponent']] = {}
    
    def __init__(self, component_id, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractDecisionComponent.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        pass
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @abstractmethod
    def decide(self, data: Dict[str, Any]) -> Tuple[str, Any]:
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        next_component, decision_basis = self.decide(data)
        data[f"{self.id}.decision_basis"] = decision_basis
        data[f"{self.id}.next_component"] = next_component
        
        return data, next_component
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {}
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "decision.next_component": {
                "type": "list",
                "description": "Chosen component ID.",
            },
            "decision.decision_basis": {
                "type": "anu",
                "description": "Evaluated decisions (up to successful one).",
            },
        }
