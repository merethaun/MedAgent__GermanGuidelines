import json
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.models.tools.llm_interaction import LLMSettings
from app.services.service_registry import get_query_transformation_service
from app.services.system.components.query_transformer.abstract_query_transformer import AbstractQueryTransformer
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)

_DEFAULT_SYSTEM_PROMPT = """You create retrieval-oriented query variants from one medical user question.

TASK:
- Produce multiple short, high-signal queries for downstream retrieval.
- Depending on the strategy, either decompose the question into subqueries or create alternative phrasings.
- Preserve the original language unless a direct medical synonym materially improves retrieval.
- Keep each output standalone and useful for vector or hybrid retrieval.
- Avoid duplicates and avoid commentary.

OUTPUT RULES:
- Return one query per line.
- Do not number the lines.
- Do not include explanations."""

_DEFAULT_PROMPT = """STRATEGY: {strategy}
MIN QUERIES: {min_queries}
MAX QUERIES: {max_queries}

QUESTION:
<query>{query}</query>

GUIDANCE:
{guidance}

OUTPUT:
Return only the queries, one per line."""


class QueryAugmenterTransformer(AbstractQueryTransformer, variant_name="query_augmenter"):
    default_parameters: Dict[str, Any] = {
        **AbstractQueryTransformer.default_parameters,
        "strategy": "decompose",
        "min_queries": 2,
        "max_queries": 4,
        "prompt": None,
        "system_prompt": None,
        "llm_settings": None,
        "session_id_key": None,
        "output_session_id_key": None,
        "guidance": (
            "For 'decompose', split the question into complementary aspects that should be retrieved separately. "
            "For 'augment', create alternative formulations that target different wording, terminology, or focus."
        ),
        "include_original_query": True,
        "deduplicate_case_insensitive": True,
    }

    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: Optional[str] = None):
        super().__init__(component_id, name, parameters, variant)
        self._last_session_id: Optional[str] = None

    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        output = getattr(result, "output", {}) or {}
        restored = output.get(f"{self.id}.session_id")
        if restored:
            self._last_session_id = str(restored)

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "strategy": {
                    "type": "string",
                    "description": "Query augmentation mode: 'decompose' for subqueries or 'augment' for alternate formulations.",
                    "default": "decompose",
                },
                "min_queries": {
                    "type": "int",
                    "description": "Minimum number of output queries requested from the model.",
                    "default": 2,
                },
                "max_queries": {
                    "type": "int",
                    "description": "Maximum number of output queries requested from the model.",
                    "default": 4,
                },
                "prompt": {
                    "type": "string",
                    "description": "Optional custom user prompt template.",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "Optional custom system prompt template.",
                },
                "llm_settings": {
                    "type": "object",
                    "description": "Unified LLM settings used for query augmentation.",
                },
                "session_id_key": {
                    "type": "string",
                    "description": "Optional workflow data key or template for reusing an LLM chat session.",
                },
                "output_session_id_key": {
                    "type": "string",
                    "description": "Optional workflow data key where the resolved session id should be stored.",
                },
                "guidance": {
                    "type": "string",
                    "description": "Additional instructions rendered into the prompt.",
                },
                "include_original_query": {
                    "type": "bool",
                    "description": "If true, keep the original query in the final output when it is not already present.",
                    "default": True,
                },
                "deduplicate_case_insensitive": {
                    "type": "bool",
                    "description": "If true, deduplicate queries case-insensitively after parsing.",
                    "default": True,
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
                "query_transformer.full_response": {"type": "string", "description": "Raw model response before parsing."},
                "query_transformer.subqueries": {
                    "type": "list",
                    "description": "Alias for the generated queries, especially useful in decomposition mode.",
                },
                "query_transformer.strategy": {
                    "type": "string",
                    "description": "Resolved augmentation strategy used for this execution.",
                },
                "query_transformer.session_id": {
                    "type": "string",
                    "description": "Session id used for this query transformer, if available.",
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

    def _resolve_session_id(self, data: Dict[str, Any]) -> str:
        key = self.parameters.get("session_id_key", self.default_parameters.get("session_id_key"))
        if key:
            if "{" in key and "}" in key:
                rendered = render_template(key, data)
                if rendered and str(rendered).strip():
                    return str(rendered).strip()
            else:
                value = data.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return self._last_session_id or f"{self.id}-{uuid4()}"

    @staticmethod
    def _parse_queries(full_response: str) -> List[str]:
        if not full_response:
            return []

        stripped = full_response.strip()
        if stripped.startswith("["):
            try:
                payload = json.loads(stripped)
                if isinstance(payload, list):
                    return [str(item).strip() for item in payload if str(item).strip()]
            except json.JSONDecodeError:
                pass

        xml_matches = re.findall(r"<query>\s*(.*?)\s*</query>", full_response, flags=re.IGNORECASE | re.DOTALL)
        if xml_matches:
            return [match.strip() for match in xml_matches if match.strip()]

        queries: List[str] = []
        for line in full_response.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
            if cleaned:
                queries.append(cleaned)
        return queries

    @staticmethod
    def _deduplicate(queries: List[str], *, case_insensitive: bool) -> List[str]:
        deduped: List[str] = []
        seen = set()
        for query in queries:
            key = " ".join(query.split()).strip()
            if not key:
                continue
            seen_key = key.lower() if case_insensitive else key
            if seen_key in seen:
                continue
            seen.add(seen_key)
            deduped.append(key)
        return deduped

    def execute(self, data: Dict[str, Any]):
        query = render_template(self.parameters.get("query", self.default_parameters["query"]), data)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Resolved query must not be empty")

        strategy = str(self.parameters.get("strategy", self.default_parameters["strategy"])).strip().lower()
        if strategy not in {"decompose", "augment"}:
            raise ValueError("strategy must be either 'decompose' or 'augment'")

        min_queries = int(self.parameters.get("min_queries", self.default_parameters["min_queries"]))
        max_queries = int(self.parameters.get("max_queries", self.default_parameters["max_queries"]))
        if min_queries < 1 or max_queries < 1 or min_queries > max_queries:
            raise ValueError("min_queries and max_queries must be >= 1 and min_queries must be <= max_queries")

        guidance = render_template(self.parameters.get("guidance", self.default_parameters["guidance"]), data)
        system_prompt = str(self.parameters.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT).strip()
        prompt = str(self.parameters.get("prompt") or _DEFAULT_PROMPT).format(
            strategy=strategy,
            min_queries=min_queries,
            max_queries=max_queries,
            query=query,
            guidance=guidance,
        ).strip()

        llm_settings = self._resolve_llm_settings(data)
        session_id = self._resolve_session_id(data)
        logger.debug(
            "QueryAugmenterTransformer.execute: component_id=%s strategy=%s session_id=%s query_chars=%d",
            self.id,
            strategy,
            session_id,
            len(query),
        )

        result = get_query_transformation_service().augment_query(
            query=query,
            system_prompt=system_prompt,
            prompt=prompt,
            llm_settings=llm_settings,
            session_id=session_id,
        )

        queries = self._parse_queries(result.full_response)
        if bool(self.parameters.get("include_original_query", self.default_parameters["include_original_query"])):
            queries.insert(0, query)
        queries = self._deduplicate(
            queries,
            case_insensitive=bool(
                self.parameters.get(
                    "deduplicate_case_insensitive",
                    self.default_parameters["deduplicate_case_insensitive"],
                ),
            ),
        )[:max_queries]
        if not queries:
            queries = [query]

        outputs = {
            **self._build_common_outputs(query, queries),
            "system_prompt": result.system_prompt,
            "prompt": result.prompt,
            "full_response": result.full_response,
            "subqueries": queries,
            "strategy": strategy,
            "session_id": result.session_id,
        }

        output_session_id_key = self.parameters.get(
            "output_session_id_key",
            self.default_parameters.get("output_session_id_key"),
        ) or f"{self.id}.session_id"
        data[output_session_id_key] = result.session_id
        self._last_session_id = result.session_id
        for key, value in outputs.items():
            data[f"{self.id}.{key}"] = value

        logger.info(
            "QueryAugmenterTransformer succeeded: component_id=%s strategy=%s queries=%d",
            self.id,
            strategy,
            len(queries),
        )
        return data, self.next_component_id
