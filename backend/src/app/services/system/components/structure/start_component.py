from typing import Any, Dict, List, Tuple

from app.models.system.system_chat_interaction import Chat, ChatInteraction, WorkflowComponentExecutionResult
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
    
    @staticmethod
    def _extract_final_output(interaction: ChatInteraction) -> str:
        generator_output = (interaction.generator_output or "").strip()
        if generator_output:
            return generator_output
        
        for execution in reversed(interaction.workflow_execution or []):
            payload = execution.output or {}
            end_response = payload.get("end.response")
            if isinstance(end_response, str) and end_response.strip():
                return end_response.strip()
        return ""
    
    def _build_previous_interactions(self, chat: Chat) -> List[Dict[str, str]]:
        interactions: List[Dict[str, str]] = []
        for idx, interaction in enumerate((chat.interactions or [])[:-1], start=1):
            user_input = " ".join((interaction.user_input or "").split()).strip()
            final_output = " ".join(self._extract_final_output(interaction).split()).strip()
            if not user_input and not final_output:
                continue
            
            item: Dict[str, str] = {"turn": str(idx)}
            if user_input:
                item["user_input"] = user_input
            if final_output:
                item["system_output"] = final_output
            interactions.append(item)
        return interactions
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        chat = render_template("{chat}", data)
        if not isinstance(chat, Chat):
            raise TypeError(f"Chat object must be of type 'Chat', but is {type(chat)}")
        
        if not chat.interactions:
            raise ValueError("Chat history is empty, expected at least one message")
        last_message = chat.interactions[-1].user_input
        logger.debug(
            "StartComponent.execute: component_id=%s interactions=%d last_input_chars=%d",
            self.id,
            len(chat.interactions),
            len(last_message or ""),
        )
        
        data[f"{self.id}.current_user_input"] = last_message
        data[f"{self.id}.previous_interactions"] = self._build_previous_interactions(chat)
        data[f"{self.id}.previous_interaction_count"] = len(data[f"{self.id}.previous_interactions"])
        logger.info(
            "StartComponent succeeded: component_id=%s previous_interactions=%d current_input=%r",
            self.id,
            data[f"{self.id}.previous_interaction_count"],
            " ".join((last_message or "").split())[:120],
        )
        
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
            "start.previous_interactions": {
                "type": "list",
                "description": "Normalized previous chat turns with user_input and final system_output, excluding the current interaction.",
            },
            "start.previous_interaction_count": {
                "type": "int",
                "description": "Number of normalized previous interactions available to downstream components.",
            },
        }
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {}
