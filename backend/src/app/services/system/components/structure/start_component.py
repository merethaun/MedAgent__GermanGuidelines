from typing import Any, Dict, Tuple

from app.models.system.system_chat_interaction import Chat, WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


class StartComponent(AbstractComponent, variant_name="start"):
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        
        self.next_component_id = None
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        chat = render_template("{chat}", data)
        if not isinstance(chat, Chat):
            raise TypeError(f"Chat object must be of type 'Chat', but is {type(chat)}")
        
        if not chat.interactions:
            raise ValueError("Chat history is empty, expected at least one message")
        last_message = chat.interactions[-1].user_input
        
        # logger.debug(f"Start chat iteration with user input: {last_message}")
        data[f"{self.id}.current_user_input"] = last_message
        
        return data, self.next_component_id
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "start.chat": {
                "type": "Chat",
                "description": "Reference to the chat object under the 'start' namespace (or whatever the id of the component is)",
            },
            "start.current_user_input": {
                "type": "string",
                "description": "Content of the last user message (must be of type QUESTION) under the 'start' namespace (or whatever the id of the component is)",
            },
        }
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {}
