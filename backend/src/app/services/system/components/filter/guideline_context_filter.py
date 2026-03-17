from typing import Any, Dict, List, Tuple

from app.models.knowledge.guideline.guideline_reference import GuidelineReference
from pydantic import TypeAdapter
from app.models.tools.guideline_context_filter import GuidelineContextFilterRequest, GuidelineContextFilterSettings
from app.services.service_registry import get_guideline_context_filter_service
from app.services.system.components.filter.abstract_filter import AbstractFilter
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)
_REFERENCE_ADAPTER = TypeAdapter(GuidelineReference)


def _render_value(value: Any, data: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_template(value, data)
    if isinstance(value, dict):
        return {key: _render_value(inner_value, data) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [_render_value(item, data) for item in value]
    return value

class _GuidelineContextFilterBase(AbstractFilter):
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_output_spec()
        base.update(
            {
                "filter.dropped_references": {
                    "type": "array",
                    "description": "References removed by the filter.",
                },
                "filter.latency": {
                    "type": "float",
                    "description": "Filter latency in seconds.",
                },
                "filter.filter_input": {
                    "type": "string",
                    "description": "Resolved input used for the filter decision.",
                },
            },
        )
        return base

    def _execute_request(
            self,
            data: Dict[str, Any],
            *,
            call_name: str,
    ) -> Tuple[Dict[str, Any], str]:
        service = get_guideline_context_filter_service()
        references = self._resolve_references(data)
        filter_input = render_template(self.parameters.get("filter_input", ""), data)
        raw_settings = self.parameters.get("settings")
        if raw_settings is None:
            raise ValueError(f"{self.__class__.__name__} requires a 'settings' object.")

        settings = GuidelineContextFilterSettings.model_validate(_render_value(raw_settings, data))

        logger.debug(
            "%s.execute: component_id=%s kind=%s method=%s references=%d filter_input_chars=%d",
            self.__class__.__name__,
            self.id,
            settings.kind.value,
            settings.method.value,
            len(references),
            len(filter_input or ""),
        )

        request = GuidelineContextFilterRequest(
            filter_input=filter_input,
            references=references,
            settings=settings,
        )
        response = getattr(service, call_name)(request)

        data[f"{self.id}.references"] = response.kept_references
        data[f"{self.id}.dropped_references"] = response.dropped_references
        data[f"{self.id}.decisions"] = [decision.model_dump() for decision in response.decisions]
        data[f"{self.id}.filter_input"] = response.filter_input
        data[f"{self.id}.latency"] = response.latency
        return data, self.next_component_id or ""

    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        raise NotImplementedError

    def _resolve_references(self, data: Dict[str, Any]) -> List[GuidelineReference]:
        references_key = self.parameters.get("references_key")
        if not references_key:
            raise ValueError("GuidelineContextFilter requires 'references_key'.")

        if isinstance(references_key, str) and "{" in references_key and "}" in references_key:
            resolved = render_template(references_key, data)
        else:
            resolved = data.get(references_key)

        if resolved is None:
            return []
        if not isinstance(resolved, list):
            raise TypeError("Resolved references must be a list of GuidelineReference objects.")

        references: List[GuidelineReference] = []
        for item in resolved:
            if hasattr(item, "extract_content") and hasattr(item, "guideline_id"):
                references.append(item)
            else:
                references.append(_REFERENCE_ADAPTER.validate_python(item))
        return references


class DeduplicateReferencesFilter(_GuidelineContextFilterBase, variant_name="deduplicate_references"):
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return self._execute_request(data, call_name="deduplicate_references")


class RelevanceFilterReferences(_GuidelineContextFilterBase, variant_name="relevance_filter_references"):
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return self._execute_request(data, call_name="relevance_filter_references")
