import json
from typing import Any, Dict, List, Tuple

from app.models.tools.llm_interaction import LLMSettings
from app.services.system.components.decision.abstract_decision import AbstractDecisionComponent
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)

_DEFAULT_SYSTEM_PROMPT = """You decide whether a user query is within the defined system scope.

Return exactly one line in this format:
DECISION: yes|no

Then optionally on the next line:
REASON: short explanation"""

_DEFAULT_PROMPT = """SCOPE:
{scope_description}

ALLOWED EXAMPLES:
{allowed_examples}

DISALLOWED EXAMPLES:
{disallowed_examples}

QUERY:
<query>{query}</query>"""


class ScopeDecisionComponent(AbstractDecisionComponent, variant_name="is_within_scope"):
    default_parameters: Dict[str, Any] = {
        "query": "{start.current_user_input}",
        "scope_description": "",
        "allowed_examples": [],
        "disallowed_examples": [],
        "prompt": None,
        "system_prompt": None,
        "llm_settings": None,
    }

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "query": {
                "type": "string",
                "description": "Query template resolved against workflow data.",
                "default": "{start.current_user_input}",
            },
            "scope_description": {
                "type": "string",
                "description": "Natural-language description of what the workflow is allowed to handle.",
            },
            "allowed_examples": {
                "type": "list",
                "description": "Optional in-scope example queries.",
            },
            "disallowed_examples": {
                "type": "list",
                "description": "Optional out-of-scope example queries.",
            },
            "prompt": {
                "type": "string",
                "description": "Optional custom prompt template.",
            },
            "system_prompt": {
                "type": "string",
                "description": "Optional custom system prompt template.",
            },
            "llm_settings": {
                "type": "object",
                "description": "Unified LLM settings used for the scope decision.",
            },
        }

    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_output_spec()
        base.update(
            {
                "decision.query": {
                    "type": "string",
                    "description": "Resolved query evaluated for scope.",
                },
                "decision.system_prompt": {
                    "type": "string",
                    "description": "Resolved system prompt sent to the model.",
                },
                "decision.prompt": {
                    "type": "string",
                    "description": "Resolved user prompt body sent to the model.",
                },
                "decision.full_response": {
                    "type": "string",
                    "description": "Raw model response before parsing.",
                },
            },
        )
        return base

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
    def _render_examples(examples: List[str]) -> str:
        examples = [str(example).strip() for example in examples if str(example).strip()]
        return "\n".join(f"- {example}" for example in examples) if examples else "- None"

    @staticmethod
    def _parse_response(full_response: str) -> Tuple[bool, str]:
        normalized = (full_response or "").strip()
        lower = normalized.lower()
        if "decision:" in lower:
            for line in normalized.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("decision:"):
                    decision_text = stripped.split(":", 1)[1].strip().lower()
                    if decision_text in {"yes", "true", "in_scope", "in-scope"}:
                        return True, normalized
                    if decision_text in {"no", "false", "out_of_scope", "out-of-scope"}:
                        return False, normalized
        if lower.startswith("yes"):
            return True, normalized
        if lower.startswith("no"):
            return False, normalized
        raise ValueError("Could not parse scope decision. Expected yes/no style output.")

    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        query = render_template(self.parameters.get("query", self.default_parameters["query"]), data)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Resolved query must not be empty")

        scope_description = render_template(
            self.parameters.get("scope_description", self.default_parameters["scope_description"]),
            data,
        )
        if not str(scope_description).strip():
            raise ValueError("ScopeDecisionComponent requires a non-empty scope_description.")

        prompt_template = self.parameters.get("prompt") or _DEFAULT_PROMPT
        system_prompt = str(self.parameters.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT).strip()
        prompt = str(prompt_template).format(
            scope_description=scope_description,
            allowed_examples=self._render_examples(self.parameters.get("allowed_examples", [])),
            disallowed_examples=self._render_examples(self.parameters.get("disallowed_examples", [])),
            query=query,
        ).strip()

        llm_settings = self._resolve_llm_settings(data)
        full_response = self.context.llm_interaction_service.generate_text(
            llm_settings=llm_settings,
            prompt=prompt,
            system_prompt=system_prompt,
        )
        value, reason = self._parse_response(full_response)
        label = "true" if value else "false"

        data[f"{self.id}.query"] = query
        data[f"{self.id}.system_prompt"] = system_prompt
        data[f"{self.id}.prompt"] = prompt
        data[f"{self.id}.full_response"] = full_response
        self._write_outputs(data, value=value, label=label, reason=reason)
        logger.info("ScopeDecisionComponent succeeded: component_id=%s label=%s", self.id, label)
        return data, self.next_component_id or ""
