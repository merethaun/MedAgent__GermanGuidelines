from typing import Dict, Any, Tuple

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class EndComponent(AbstractComponent, variant_name="end"):
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        
        self.next_component_id = None
    
    def set_next_component(self, next_component_id: str):
        pass
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        generation_key = self.parameters.get("generation_key", "")
        if not generation_key:
            raise ValueError("EndComponent requires a 'generation_key' parameter to know what to return.")
        final_value = render_template(generation_key, data)
        data[f"{self.id}.response"] = final_value
        
        retrieval_key = self.parameters.get("retrieval_key", "")
        retrieval_latency_key = self.parameters.get("retrieval_latency_key", "")
        if not retrieval_key:
            logger.info(f"EndComponent has no configured 'retrieval_key', so no return value to be expected")
            data[f"{self.id}.retrieval"] = None
            data[f"{self.id}.retrieval_latency"] = None
        else:
            if not retrieval_latency_key:
                raise ValueError("EndComponent requires a 'retrieval_latency_key' IF working with retrieval.")
            retrieval_value = render_template(retrieval_key, data)
            retrieval_latency_value = render_template(retrieval_latency_key, data)
            data[f"{self.id}.retrieval"] = retrieval_value
            data[f"{self.id}.retrieval_latency"] = retrieval_latency_value
        return data, ""
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "generation_key": {
                "type": "string",
                "description": "Path in the data dict to return as the final generation result "
                               "(e.g., 'default_gen.response')",
            },
            "retrieval_key": {
                "type": "string",
                "description": "Path in the data dict to return as the retrieved entities, OPTIONAL!; "
                               "Expects a dict with keys: source_id, retrieval, reference_id",
            },
            "retrieval_latency_key": {
                "type": "string",
                "description": "Path in the data dict to return the latency caused by retrieval, OPTIONAL! (but must "
                               "with retrieval_key in combination)",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "end.response": {
                "type": "Any",
                "description": "The final value extracted using 'generation_key', stored under this component's name",
            },
            "end.retrieval": {
                "type": "Any",
                "description": "Forwards the retrieval result as specified in 'retrieval key'. Just like the key, this output is optional!",
            },
            "end.retrieval_latency": {
                "type": "Any",
                "description": "Forwards the latency caused by retrieval. Just like the key, this output is optional!",
            },
        }
