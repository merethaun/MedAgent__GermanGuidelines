from abc import abstractmethod
from typing import Dict, Type, Any, Optional, Tuple

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AbstractGenerator(AbstractComponent, variant_name="generator"):
    variants: Dict[str, Type['AbstractGenerator']] = {}
    
    default_parameters: Dict[str, Any] = {"prompt": "f'{start.current_user_input}'"}
    
    def __init__(self, component_id, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractGenerator.variants[variant_name] = cls
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    @abstractmethod
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "prompt": {
                "type": "string",
                "description": "Prompt template to use for the generation (will be resolved with the variables specified)",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "generator.response": {
                "type": "string",
                "description": "Generated text based on the resolved prompt, available under namespace of component",
            },
            "generator.prompt": {
                "type": "string",
                "description": "More for logging purposes: return what the generator received as prompt",
            },
        }
    
    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        prompt_template = self.parameters.get("prompt", self.default_parameters.get("prompt"))
        prompt = render_template(prompt_template, data)
        
        logger.debug(f"Resolved to\n{prompt}")
        
        data[f"{self.id}.prompt"] = prompt
        response = self.generate_response(prompt)
        data[f"{self.id}.response"] = response
        
        logger.debug(f"Generated response:\n{response}")
        
        return data, self.next_component_id
