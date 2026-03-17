import json
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from app.models.system import PromptDefinition
from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.models.tools.llm_interaction import LLMSettings
from app.services.service_registry import get_query_transformation_service
from app.services.system.components.query_transformer.abstract_query_transformer import AbstractQueryTransformer
from app.services.system.prompt_store import get_prompt_definition
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)

_DEFAULT_HYDE_SYSTEM_PROMPT = """You generate concise hypothetical documents ("HyDE") for retrieval augmentation.

TASK:
- Generate short, useful hypothetical documents for the user's query.
- Prefer German guideline-style passages.
- Each document should be self-contained and retrieval-oriented.
- Keep the output grounded in the stated domain and avoid irrelevant fabrication.

DOMAIN HINT:
{document_description}

FORMAT REQUIREMENTS:
- Output only <document>...</document> blocks.
- Generate at most {num_documents} documents.
- Keep each document at most {target_tokens} tokens.
- If no useful document can be generated, return an empty string."""

_DEFAULT_HYDE_PROMPT = """{few_shot_examples}QUESTION:
\"\"\"{query}\"\"\"

OUTPUT:
Return AT MOST {num_documents} <document>...</document> blocks."""


class HyDEQueryTransformer(AbstractQueryTransformer, variant_name="hyde"):
    default_parameters: Dict[str, Any] = {
        **AbstractQueryTransformer.default_parameters,
        "prompt": None,
        "prompt_key": "hyde_awmf_query_transform_v1",
        "system_prompt": None,
        "system_prompt_key": "hyde_awmf_query_transform_v1",
        "llm_settings": None,
        "session_id_key": None,
        "output_session_id_key": None,
        "num_documents": 1,
        "target_tokens": 220,
        "document_description": (
            "Generate short German guideline-style passages for Oral and Maxillofacial surgery topics from the AWMF. "
            "Prefer definitions, indications, diagnostics, contraindications, and first-line therapy language. "
            "If the query is out of scope, avoid fabricating detailed content."
        ),
        "examples": [],
        "min_chars": 64,
        "max_similarity": 0.9,
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
                "prompt": {
                    "type": "string",
                    "description": "Prompt body sent after the system prompt. Should usually contain only the query and optional examples.",
                },
                "prompt_key": {
                    "type": "string",
                    "description": "Lookup key for a shared prompt definition stored in the prompt registry.",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "System instructions for HyDE generation. Prefer putting stable HyDE instructions here.",
                },
                "system_prompt_key": {
                    "type": "string",
                    "description": "Lookup key for the system prompt stored in the prompt registry.",
                },
                "llm_settings": {
                    "type": "object",
                    "description": "Unified LLM settings used for HyDE generation.",
                },
                "session_id_key": {
                    "type": "string",
                    "description": "Optional workflow data key or template for reusing an LLM chat session.",
                },
                "output_session_id_key": {
                    "type": "string",
                    "description": "Optional workflow data key where the resolved session id should be stored.",
                },
                "num_documents": {"type": "int", "description": "Maximum number of hypothetical documents to generate.", "default": 1},
                "target_tokens": {
                    "type": "int", "description": "Instructional upper bound for the size of each hypothetical document.", "default": 220,
                },
                "document_description": {"type": "string", "description": "Domain/style hint for the generated hypothetical documents."},
                "examples": {
                    "type": "list",
                    "description": "Few-shot examples shaped as [{'query': str, 'documents': str | list[str]}].",
                    "default": [],
                },
                "min_chars": {"type": "int", "description": "Discard very short generated documents.", "default": 64},
                "max_similarity": {
                    "type": "float", "description": "Discard near-duplicate hypothetical documents above this similarity threshold.", "default": 0.9,
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
                "query_transformer.documents": {"type": "list", "description": "Filtered hypothetical documents extracted from <document> blocks."},
                "query_transformer.session_id": {
                    "type": "string",
                    "description": "Session id used for this query transformer, if session-backed execution is available.",
                },
            },
        )
        return base
    
    def _resolve_prompt_definition(self) -> Optional[PromptDefinition]:
        prompt_key = self.parameters.get("prompt_key", self.default_parameters.get("prompt_key"))
        system_prompt_key = self.parameters.get("system_prompt_key", self.default_parameters.get("system_prompt_key"))
        if prompt_key and system_prompt_key and prompt_key != system_prompt_key:
            raise ValueError("prompt_key and system_prompt_key must match when both are provided")
        key = prompt_key or system_prompt_key
        return get_prompt_definition(key) if key else None
    
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
    def _render_examples(examples: List[Dict[str, Union[str, List[str]]]]) -> str:
        rendered = []
        for i, example in enumerate(examples or []):
            query = str(example.get("query", "")).strip()
            documents = example.get("documents", [])
            if isinstance(documents, str):
                documents = [documents]
            documents = [str(doc).strip() for doc in documents if str(doc).strip()]
            if not query or not documents:
                continue
            document_blocks = "\n".join(f"<document>\n{doc}\n</document>" for doc in documents)
            rendered.append(f"Example {i + 1}:\nQUESTION: {query}\nOUTPUT:\n{document_blocks}")
        if not rendered:
            return ""
        return "---\nFEW-SHOT EXAMPLES:\n" + "\n\n".join(rendered) + "\n---\n\n"
    
    def execute(self, data: Dict[str, Any]):
        query = render_template(self.parameters.get("query", self.default_parameters["query"]), data)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Resolved query must not be empty")
        
        prompt_definition = self._resolve_prompt_definition()
        system_prompt_template = self._resolve_prompt_template("system_prompt", prompt_definition)
        prompt_template = self._resolve_prompt_template("prompt", prompt_definition)
        render_context = {
            "num_documents": self.parameters.get("num_documents", self.default_parameters["num_documents"]),
            "target_tokens": self.parameters.get("target_tokens", self.default_parameters["target_tokens"]),
            "document_description": render_template(
                self.parameters.get("document_description", self.default_parameters["document_description"]),
                data,
            ),
        }
        system_prompt = str(system_prompt_template or _DEFAULT_HYDE_SYSTEM_PROMPT).format(**render_context)
        prompt = str(prompt_template or _DEFAULT_HYDE_PROMPT).format(
            query=query,
            num_documents=render_context["num_documents"],
            few_shot_examples=self._render_examples(self.parameters.get("examples", self.default_parameters["examples"])),
        ).strip()
        
        llm_settings = self._resolve_llm_settings(data)
        session_id = self._resolve_session_id(data)
        logger.debug(
            "HyDEQueryTransformer.execute: component_id=%s session_id=%s model=%s query_chars=%d num_documents=%s target_tokens=%s",
            self.id,
            session_id,
            llm_settings.model,
            len(query),
            render_context["num_documents"],
            render_context["target_tokens"],
        )
        result = get_query_transformation_service().generate_hyde_documents(
            query=query,
            system_prompt=system_prompt,
            prompt=prompt,
            llm_settings=llm_settings,
            session_id=session_id,
            min_chars=self.parameters.get("min_chars", self.default_parameters["min_chars"]),
            max_similarity=self.parameters.get("max_similarity", self.default_parameters["max_similarity"]),
        )
        
        outputs = {
            **self._build_common_outputs(query, result.documents),
            "system_prompt": result.system_prompt,
            "prompt": result.prompt,
            "full_response": result.full_response,
            "documents": result.documents,
            "session_id": result.session_id,
        }
        
        output_session_id_key = self.parameters.get(
            "output_session_id_key", self.default_parameters.get("output_session_id_key"),
        ) or f"{self.id}.session_id"
        data[output_session_id_key] = result.session_id
        self._last_session_id = result.session_id
        for key, value in outputs.items():
            data[f"{self.id}.{key}"] = value
        logger.info(
            "HyDEQueryTransformer succeeded: component_id=%s session_id=%s documents=%d",
            self.id,
            result.session_id,
            len(result.documents or []),
        )
        return data, self.next_component_id
