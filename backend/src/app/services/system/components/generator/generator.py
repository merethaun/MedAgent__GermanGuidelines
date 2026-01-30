import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.exceptions.tools import LLMChatSessionNotFoundError
from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.models.tools.llm_interaction import LLMSettings, Message
from app.services.system.components import AbstractComponent
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


def _coerce_llm_settings(raw: Any) -> LLMSettings:
    """
    Accept LLMSettings or dict or JSON-stringified dict.
    """
    if isinstance(raw, LLMSettings):
        return raw
    
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError("llm_settings must be dict/LLMSettings or JSON string of a dict") from e
    
    if not isinstance(raw, dict):
        raise TypeError(f"llm_settings must be dict/LLMSettings, got {type(raw)}")
    
    return LLMSettings.model_validate(raw)


def _render_llm_settings(raw: Any, data: Dict[str, Any]) -> Any:
    """
    Render templated string values inside llm_settings (optional convenience).
    """
    if isinstance(raw, str):
        return render_template(raw, data)
    if isinstance(raw, dict):
        return {k: _render_llm_settings(v, data) for k, v in raw.items()}
    if isinstance(raw, list):
        return [_render_llm_settings(v, data) for v in raw]
    return raw


class LLMGenerator(AbstractComponent, variant_name="generator"):
    """
    Generator that delegates all conversation state to LLMInteractionService.

    Conversation continuation:
    - Works as long as the same `session_id` is reused across workflow executions.
    - The generator can (a) read it from workflow data or (b) generate one and write it back.

    Note: still in-memory overall because LLMInteractionService is in-memory.
    """
    
    default_parameters: Dict[str, Any] = {
        "prompt": "{start.current_user_input}",
        "system_prompt": None,
        
        # Settings:
        "llm_settings": None,
        
        # Session:
        # Can be a data key ("chat.session_id") OR a template ("{chat.id}")
        "session_id_key": None,
        "output_session_id_key": "generator.session_id",
        
        # Optional session seeding:
        # Provide list[Message] from workflow data on FIRST session creation.
        "initial_history_key": None,  # e.g. "chat.seed_history"
        "max_initial_history_messages": 50,
        
        # If you want to reset on each run (usually false)
        "reset_history_each_run": False,
        
        # If llm_settings changes, update the session automatically
        "update_settings_each_run": True,
    }
    
    def __init__(
            self,
            component_id,
            name: str,
            parameters: Dict[str, Any],
            variant: str = None,
    ):
        super().__init__(component_id, name, parameters, variant)
        self._last_execution_result: Optional[WorkflowComponentExecutionResult] = None
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        self._last_execution_result = result
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "prompt": {
                "type": "string",
                "description": "Prompt template resolved against workflow data.",
            },
            "system_prompt": {
                "type": "string",
                "description": "Optional system prompt (only used on session creation).",
            },
            "llm_settings": {
                "type": "object",
                "description": "Unified LLMSettings (LiteLLM).",
            },
            "session_id_key": {
                "type": "string",
                "description": "Workflow data key or template used as stable session id. If missing/empty, a UUID is generated.",
            },
            "output_session_id_key": {
                "type": "string",
                "description": "Where to write the resolved/generated session id into workflow data.",
            },
            "initial_history_key": {
                "type": "string",
                "description": "Optional workflow data key containing list[Message] used only when creating a new session.",
            },
            "max_initial_history_messages": {
                "type": "int",
                "description": "Trim initial history to last N messages.",
            },
            "reset_history_each_run": {
                "type": "bool",
                "description": "If true, resets history every execute().",
            },
            "update_settings_each_run": {
                "type": "bool",
                "description": "If true, updates session settings each run.",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "generator.response": {
                "type": "string",
                "description": "Generated response text.",
            },
            "generator.prompt": {
                "type": "string",
                "description": "Resolved prompt that was sent.",
            },
            "generator.session_id": {
                "type": "string",
                "description": "Session id used for conversation continuation.",
            },
            "generator.history": {
                "type": "array",
                "description": "Current session history after the call.",
            },
        }
    
    # -------------------------
    # Resolution helpers
    # -------------------------
    def _resolve_llm_settings(self, data: Dict[str, Any]) -> LLMSettings:
        raw = self.parameters.get("llm_settings", self.default_parameters["llm_settings"])
        if raw is None:
            raise ValueError("No llm_settings provided. Set parameters.llm_settings.")
        raw = _render_llm_settings(raw, data)
        return _coerce_llm_settings(raw)
    
    def _resolve_session_id(self, data: Dict[str, Any]) -> str:
        key = self.parameters.get("session_id_key", self.default_parameters["session_id_key"])
        out_key = self.parameters.get("output_session_id_key", self.default_parameters["output_session_id_key"])
        
        sid: Optional[str] = None
        
        if key:
            # key can be a template or a direct data key
            if "{" in key and "}" in key:
                sid = render_template(key, data).strip() or None
            else:
                val = data.get(key)
                sid = str(val).strip() if val is not None else None
        
        if not sid:
            sid = str(uuid4())
        
        if out_key:
            data[out_key] = sid
        
        return sid
    
    def _resolve_initial_history(self, data: Dict[str, Any]) -> Optional[List[Message]]:
        key = self.parameters.get("initial_history_key", self.default_parameters["initial_history_key"])
        if not key:
            return None
        
        hist = data.get(key)
        if hist is None:
            return None
        if not isinstance(hist, list):
            raise TypeError(f"initial_history_key='{key}' must point to a list[Message]")
        
        max_n = int(
            self.parameters.get(
                "max_initial_history_messages",
                self.default_parameters["max_initial_history_messages"],
            ),
        )
        if max_n > 0:
            hist = hist[-max_n:]
        
        # minimal validation
        for m in hist:
            if not (isinstance(m, dict) and "role" in m and "content" in m):
                raise ValueError(f"Invalid message in initial history at {key}: {m!r}")
        
        return hist
    
    # -------------------------
    # Session management (delegated to LLMInteractionService)
    # -------------------------
    def _ensure_session(
            self,
            *,
            session_id: str,
            llm_settings: LLMSettings,
            system_prompt: Optional[str],
            initial_history: Optional[List[Message]],
            update_settings_each_run: bool,
            reset_history_each_run: bool,
    ) -> None:
        """
        Ensure a session exists; create on first use.
        Optionally update settings + reset history.
        """
        try:
            # If session exists, optionally update settings / reset history.
            if update_settings_each_run:
                self.context.llm_interaction_service.update_session_settings(session_id, llm_settings)
            if reset_history_each_run:
                self.context.llm_interaction_service.reset_history(session_id, keep_system_prompt=True)
        except LLMChatSessionNotFoundError:
            # Create on first use
            self.context.llm_interaction_service.create_session(
                llm_settings=llm_settings,
                session_id=session_id,
                system_prompt=system_prompt,
                initial_history=initial_history,
            )
    
    def _chat_once(self, *, session_id: str, prompt: str) -> str:
        """
        Separated client interaction: one place that performs the chat call.
        """
        return self.context.llm_interaction_service.chat_text(session_id=session_id, prompt=prompt)
    
    # -------------------------
    # Execution
    # -------------------------
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        prompt_template = self.parameters.get("prompt", self.default_parameters["prompt"])
        prompt = render_template(prompt_template, data)
        
        if not prompt.strip():
            raise ValueError("Resolved prompt must not be empty")
        
        llm_settings = self._resolve_llm_settings(data)
        session_id = self._resolve_session_id(data)
        
        system_prompt = self.parameters.get("system_prompt", self.default_parameters["system_prompt"])
        if system_prompt:
            system_prompt = render_template(system_prompt, data)
        
        initial_history = self._resolve_initial_history(data)
        
        update_settings_each_run = bool(
            self.parameters.get(
                "update_settings_each_run", self.default_parameters["update_settings_each_run"],
            ),
        )
        reset_history_each_run = bool(
            self.parameters.get(
                "reset_history_each_run", self.default_parameters["reset_history_each_run"],
            ),
        )
        
        self._ensure_session(
            session_id=session_id,
            llm_settings=llm_settings,
            system_prompt=system_prompt,
            initial_history=initial_history,
            update_settings_each_run=update_settings_each_run,
            reset_history_each_run=reset_history_each_run,
        )
        
        logger.info(
            "LLMGenerator: component_id=%s session_id=%s model=%s base_url=%s prompt_chars=%d",
            self.id,
            session_id,
            llm_settings.model,
            llm_settings.base_url,
            len(prompt),
        )
        
        response = self._chat_once(session_id=session_id, prompt=prompt)
        
        # Outputs
        data[f"{self.id}.prompt"] = prompt
        data[f"{self.id}.response"] = response
        data[f"{self.id}.session_id"] = session_id
        data[f"{self.id}.history"] = self.context.llm_interaction_service.get_history(session_id)
        
        return data, self.next_component_id
