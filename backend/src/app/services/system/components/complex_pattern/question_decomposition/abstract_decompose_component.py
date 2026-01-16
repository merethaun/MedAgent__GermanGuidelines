from abc import ABC
from typing import Dict, Type, Any, Optional

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AbstractDecomposeComponent(AbstractComponent, ABC, variant_name="decompose"):
    variants: Dict[str, Type['AbstractDecomposeComponent']] = {}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractDecomposeComponent.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        # TODO: add history of previous processing??
        pass
