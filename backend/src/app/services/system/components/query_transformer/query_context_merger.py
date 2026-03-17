import json
from typing import Any, Dict, List, Optional

from app.models.system import PromptDefinition
from app.models.system.system_chat_interaction import Chat, WorkflowComponentExecutionResult
from app.models.tools.llm_interaction import LLMSettings
from app.services.service_registry import get_query_transformation_service
from app.services.system.components.query_transformer.abstract_query_transformer import AbstractQueryTransformer
from app.services.system.prompt_store import get_prompt_definition
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)

_DEFAULT_QUERY_CONTEXT_MERGER_SYSTEM_PROMPT = """You merge the current user query with recent conversation context when it is relevant.

TASK:
- Produce one standalone query for downstream workflow steps.
- Use recent history only if it helps resolve references, ellipses, follow-up questions, or missing context.
- Ignore history that is unrelated to the new query.
- Preserve the original language, medical terminology, and intent.
- Keep the result concise and directly usable for retrieval or later rewriting.

OUTPUT RULE:
Return only the merged query."""

_DEFAULT_QUERY_CONTEXT_MERGER_PROMPT = """CURRENT QUERY:
<query>{query}</query>

RECENT CONTEXT:
{history_block}

OUTPUT:
Return only one merged standalone query.
If the history is not relevant, return the current query unchanged."""


class QueryContextMergerTransformer(AbstractQueryTransformer, variant_name="query_context_merger"):
    default_parameters: Dict[str, Any] = {
        **AbstractQueryTransformer.default_parameters,
        "prompt": None,
        "prompt_key": None,
        "system_prompt": None,
        "llm_settings": None,
        "max_history_items": 3,
        "max_output_chars": 500,
        "history_items_key": "start.previous_interactions",
    }
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "prompt": {
                    "type": "string",
                    "description": "Prompt body sent after the system prompt. Usually includes the current query and rendered history block.",
                },
                "prompt_key": {
                    "type": "string",
                    "description": "Lookup key for a shared prompt definition stored in the prompt registry.",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "System instructions for the query context merger.",
                },
                "llm_settings": {
                    "type": "object",
                    "description": "Unified LLM settings used for the merger/compression step.",
                },
                "max_history_items": {
                    "type": "int",
                    "description": "How many previous interactions to inspect before the current query.",
                    "default": 3,
                },
                "max_output_chars": {
                    "type": "int",
                    "description": "Trim each previous system output to this many characters before sending it to the LLM.",
                    "default": 500,
                },
                "history_items_key": {
                    "type": "string",
                    "description": "Workflow data key containing normalized previous interactions. Defaults to start.previous_interactions.",
                    "default": "start.previous_interactions",
                },
            },
        )
        return base
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_output_spec()
        base.update(
            {
                "query_transformer.system_prompt": {"type": "string", "description": "Resolved system prompt sent to the model."},
                "query_transformer.prompt": {"type": "string", "description": "Resolved user prompt body sent to the model."},
                "query_transformer.full_response": {"type": "string", "description": "Raw model response before post-processing."},
                "query_transformer.merged_query": {
                    "type": "string", "description": "Final standalone query produced from current input plus optional history.",
                },
                "query_transformer.history_items": {"type": "list", "description": "Rendered history items included in this compression step."},
                "query_transformer.history_item_count": {"type": "int", "description": "Number of previous interactions used for the context merge."},
            },
        )
        return base
    
    def _resolve_prompt_definition(self) -> Optional[PromptDefinition]:
        prompt_key = self.parameters.get("prompt_key", self.default_parameters.get("prompt_key"))
        return get_prompt_definition(prompt_key) if prompt_key else None
    
    def _resolve_prompt_template(self, template_param: str, definition: Optional[PromptDefinition]) -> Any:
        if template_param in self.parameters and self.parameters[template_param] is not None:
            return self.parameters[template_param]
        if definition is not None:
            return getattr(definition, template_param)
        return self.parameters.get(template_param, self.default_parameters.get(template_param))
    
    def _resolve_llm_settings(self, data: Dict[str, Any]) -> LLMSettings:
        raw = self.parameters.get("llm_settings", self.default_parameters["llm_settings"])
        if raw is None:
            raise ValueError("No llm_settings provided. Set parameters.llm_settings.")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            rendered = {
                key: render_template(value, data) if isinstance(value, str) else value
                for key, value in raw.items()
            }
            return LLMSettings.model_validate(rendered)
        return LLMSettings.model_validate(raw)
    
    @staticmethod
    def _shorten(text: str, max_chars: int) -> str:
        if max_chars <= 0:
            return text.strip()
        text = " ".join((text or "").split()).strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."
    
    def _fallback_history_items(self, data: Dict[str, Any]) -> List[Dict[str, str]]:
        chat = data.get("chat")
        if not isinstance(chat, Chat):
            return []
        return [
            {
                "turn": str(idx),
                "user_input": " ".join((interaction.user_input or "").split()).strip(),
                "system_output": " ".join((interaction.generator_output or "").split()).strip(),
            }
            for idx, interaction in enumerate((chat.interactions or [])[:-1], start=1)
            if (interaction.user_input or "").strip() or (interaction.generator_output or "").strip()
        ]
    
    def _build_history_items(self, data: Dict[str, Any]) -> List[Dict[str, str]]:
        key = self.parameters.get("history_items_key", self.default_parameters["history_items_key"])
        raw_history = data.get(key) if key else None
        if raw_history is None:
            raw_history = self._fallback_history_items(data)
        
        if not isinstance(raw_history, list):
            raise TypeError(f"history_items_key='{key}' must point to a list")
        
        max_history_items = int(self.parameters.get("max_history_items", self.default_parameters["max_history_items"]))
        if max_history_items <= 0:
            return []
        
        max_output_chars = int(self.parameters.get("max_output_chars", self.default_parameters["max_output_chars"]))
        selected = raw_history[-max_history_items:]
        history_items: List[Dict[str, str]] = []
        for item in selected:
            if not isinstance(item, dict):
                continue
            user_input = " ".join(str(item.get("user_input", "")).split()).strip()
            system_output = self._shorten(str(item.get("system_output", "")), max_output_chars)
            turn = str(item.get("turn", len(history_items) + 1))
            if not user_input and not system_output:
                continue
            rendered_item: Dict[str, str] = {"turn": turn}
            if user_input:
                rendered_item["user_input"] = user_input
            if system_output:
                rendered_item["system_output"] = system_output
            history_items.append(rendered_item)
        return history_items
    
    @staticmethod
    def _render_history_block(history_items: List[Dict[str, str]]) -> str:
        if not history_items:
            return "<history>\nNo previous interactions available.\n</history>"
        
        lines = ["<history>"]
        for item in history_items:
            lines.append(f"<interaction index=\"{item['turn']}\">")
            if item.get("user_input"):
                lines.append(f"<user_input>{item['user_input']}</user_input>")
            if item.get("system_output"):
                lines.append(f"<system_output>{item['system_output']}</system_output>")
            lines.append("</interaction>")
        lines.append("</history>")
        return "\n".join(lines)
    
    def execute(self, data: Dict[str, Any]):
        query = render_template(self.parameters.get("query", self.default_parameters["query"]), data)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Resolved query must not be empty")
        
        history_items = self._build_history_items(data)
        history_block = self._render_history_block(history_items)
        llm_settings = self._resolve_llm_settings(data)
        logger.debug(
            "QueryContextMerger.execute: component_id=%s model=%s query_chars=%d history_items=%d max_history_items=%s",
            self.id,
            llm_settings.model,
            len(query),
            len(history_items),
            self.parameters.get("max_history_items", self.default_parameters["max_history_items"]),
        )
        
        prompt_definition = self._resolve_prompt_definition()
        system_prompt_template = self._resolve_prompt_template("system_prompt", prompt_definition)
        prompt_template = self._resolve_prompt_template("prompt", prompt_definition)
        
        system_prompt = str(system_prompt_template or _DEFAULT_QUERY_CONTEXT_MERGER_SYSTEM_PROMPT).strip()
        prompt = str(prompt_template or _DEFAULT_QUERY_CONTEXT_MERGER_PROMPT).format(
            query=query,
            history_block=history_block,
        ).strip()
        
        result = get_query_transformation_service().merge_query_with_history(
            query=query,
            system_prompt=system_prompt,
            prompt=prompt,
            llm_settings=llm_settings,
        )
        
        outputs = {
            **self._build_common_outputs(query, [result.merged_query] if result.merged_query else []),
            "system_prompt": result.system_prompt,
            "prompt": result.prompt,
            "full_response": result.full_response,
            "merged_query": result.merged_query,
            "history_items": history_items,
            "history_item_count": len(history_items),
        }
        
        for key, value in outputs.items():
            data[f"{self.id}.{key}"] = value
        logger.info(
            "QueryContextMerger succeeded: component_id=%s merged_query_chars=%d history_items=%d",
            self.id,
            len(result.merged_query or ""),
            len(history_items),
        )
        return data, self.next_component_id
