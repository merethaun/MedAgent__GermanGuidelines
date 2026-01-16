from typing import Dict, Any, Tuple

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class CodeExecutorComponent(AbstractComponent, variant_name="code_executor"):
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        
        self.next_component_id = None
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        Execute the component for each value in the list and collect results.
        """
        code = self.parameters.get("code", "")
        code_output = render_template(code, data)
        data[f"{self.id}.code_output"] = code_output
        return data, self.next_component_id
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "code": {
                "type": "str",
                "description": "Code to execute with data accessed via statements like `generator.response`.",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "code_executor.code_output": {
                "type": "any",
                "description": "Whatever for returned by the code provided.",
            },
        }
