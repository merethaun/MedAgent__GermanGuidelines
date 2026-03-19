import time
from typing import Any, Dict, List, Tuple

from pydantic import TypeAdapter

from app.models.knowledge.guideline.guideline_reference import GuidelineReference
from app.models.system.workflow_expander import GraphReferenceExpanderSettings, GuidelineExpanderSettings
from app.models.tools.guideline_expander import GuidelineExpanderRequest
from app.services.service_registry import get_graph_service, get_guideline_expander_service
from app.services.system.components.context_expander.abstract_expander import AbstractExpander
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

_REFERENCE_ADAPTER = TypeAdapter(GuidelineReference)
logger = setup_logger(__name__)


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


class GraphReferencesExpander(_ReferenceExpanderBase, variant_name="graph_references"):
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_output_spec()
        base.update(
            {
                "expander.graph_hits": {
                    "type": "array",
                    "description": "Ranked graph hit explanations for the expanded references.",
                },
            },
        )
        return base

    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        references = self._resolve_references(data)
        raw_settings = self.parameters.get("settings")
        if raw_settings is None:
            raise ValueError("GraphReferencesExpander requires a 'settings' object.")

        settings = GraphReferenceExpanderSettings.model_validate(_render_value(raw_settings, data))
        logger.info(
            "GraphReferencesExpander started: component_id=%s graph=%s seeds=%d limit=%d include_seed=%s neighbor_depth=%d include_section=%s include_keywords=%s include_similarity=%s",
            self.id,
            settings.graph_name,
            len(references),
            settings.limit,
            settings.include_seed_references,
            settings.neighbor_depth,
            settings.include_section_references,
            settings.include_keyword_matches,
            settings.include_similarity_matches,
        )
        expanded_references, added_references, graph_hits, latency = get_graph_service().expand_from_references(
            graph_name=settings.graph_name,
            seed_references=references,
            result_limit=settings.limit,
            include_seed_references=settings.include_seed_references,
            neighbor_depth=settings.neighbor_depth,
            include_section_references=settings.include_section_references,
            section_max_children=settings.section_max_children,
            include_keyword_matches=settings.include_keyword_matches,
            keyword_overlap_min=settings.keyword_overlap_min,
            keyword_overlap_ratio_min=settings.keyword_overlap_ratio_min,
            include_similarity_matches=settings.include_similarity_matches,
            similarity_threshold=settings.similarity_threshold,
        )
        data[f"{self.id}.references"] = expanded_references
        data[f"{self.id}.added_references"] = added_references
        data[f"{self.id}.graph_hits"] = [hit.model_dump() if hasattr(hit, "model_dump") else dict(hit) for hit in graph_hits]
        data[f"{self.id}.latency"] = latency
        logger.info(
            "GraphReferencesExpander succeeded: component_id=%s graph=%s returned=%d added=%d hits=%d latency=%.2fs",
            self.id,
            settings.graph_name,
            len(expanded_references),
            len(added_references),
            len(graph_hits),
            latency,
        )
        return data, self.next_component_id or ""
