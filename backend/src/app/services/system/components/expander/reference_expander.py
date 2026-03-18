import time
from typing import Any, Dict, List, Tuple

from app.models.knowledge.guideline.guideline_reference import GuidelineReference
from app.models.system.workflow_expander import GuidelineExpanderSettings
from app.models.tools.guideline_expander import GuidelineExpanderRequest
from app.services.service_registry import get_guideline_expander_service
from app.services.system.components.expander.abstract_expander import AbstractExpander
from app.utils.system.render_template import render_template
from pydantic import TypeAdapter

_REFERENCE_ADAPTER = TypeAdapter(GuidelineReference)


def _render_value(value: Any, data: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_template(value, data)
    if isinstance(value, dict):
        return {key: _render_value(inner_value, data) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [_render_value(item, data) for item in value]
    return value


class _ReferenceExpanderBase(AbstractExpander):
    def _resolve_references(self, data: Dict[str, Any]) -> List[GuidelineReference]:
        references_key = self.parameters.get("references_key")
        if not references_key:
            raise ValueError(f"{self.__class__.__name__} requires 'references_key'.")

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


class NeighborhoodReferencesExpander(_ReferenceExpanderBase, variant_name="neighborhood_references"):
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        started = time.time()
        references = self._resolve_references(data)
        raw_settings = self.parameters.get("settings")
        if raw_settings is None:
            raise ValueError("NeighborhoodReferencesExpander requires a 'settings' object.")

        settings = GuidelineExpanderSettings.model_validate(_render_value(raw_settings, data))
        response = get_guideline_expander_service().expand_references(
            GuidelineExpanderRequest(references=references, settings=settings),
        )
        data[f"{self.id}.references"] = response.references
        data[f"{self.id}.added_references"] = response.added_references
        data[f"{self.id}.latency"] = max(response.latency, time.time() - started)
        return data, self.next_component_id or ""


class HierarchyReferencesExpander(_ReferenceExpanderBase, variant_name="hierarchy_references"):
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        started = time.time()
        references = self._resolve_references(data)
        raw_settings = self.parameters.get("settings")
        if raw_settings is None:
            raise ValueError("HierarchyReferencesExpander requires a 'settings' object.")

        settings = GuidelineExpanderSettings.model_validate(_render_value(raw_settings, data))
        response = get_guideline_expander_service().expand_references(
            GuidelineExpanderRequest(references=references, settings=settings),
        )
        data[f"{self.id}.references"] = response.references
        data[f"{self.id}.added_references"] = response.added_references
        data[f"{self.id}.latency"] = max(response.latency, time.time() - started)
        return data, self.next_component_id or ""
