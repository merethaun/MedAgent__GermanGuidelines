from typing import Any, Dict, List, Tuple

from app.models.knowledge.guideline.guideline_reference import GuidelineReference
from app.models.system.workflow_retriever import GraphRetrieverSettings
from app.services.service_registry import get_graph_service
from app.services.system.components.retriever.abstract_retriever import AbstractRetriever
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


def _render_value(value: Any, data: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_template(value, data)
    if isinstance(value, dict):
        return {key: _render_value(inner_value, data) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [_render_value(item, data) for item in value]
    return value


class GraphRetriever(AbstractRetriever, variant_name="graph_retriever"):
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "settings": {
                    "type": "object",
                    "description": "GraphRetrieverSettings payload used for Neo4j graph retrieval.",
                },
            },
        )
        return base

    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_output_spec()
        base.update(
            {
                "retriever.latency": {
                    "type": "float",
                    "description": "Neo4j graph retrieval latency in seconds.",
                },
                "retriever.graph_hits": {
                    "type": "array",
                    "description": "Ranked graph hit explanations for the returned references.",
                },
            },
        )
        return base

    def _resolve_settings(self, data: Dict[str, Any]) -> GraphRetrieverSettings:
        raw_settings = self.parameters.get("settings")
        if raw_settings is None:
            raise ValueError("GraphRetriever requires a 'settings' object.")
        rendered = _render_value(raw_settings, data)
        return GraphRetrieverSettings.model_validate(rendered)

    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[List[GuidelineReference], float]:
        settings = self._resolve_settings(data)
        logger.info(
            "GraphRetriever started: component_id=%s graph=%s query_chars=%d seed_limit=%d result_limit=%d neighbor_depth=%d include_section=%s include_keywords=%s include_similarity=%s",
            self.id,
            settings.graph_name,
            len(query),
            settings.seed_limit,
            settings.limit,
            settings.neighbor_depth,
            settings.include_section_references,
            settings.include_keyword_matches,
            settings.include_similarity_matches,
        )
        references, hits, latency = get_graph_service().retrieve_references(
            graph_name=settings.graph_name,
            query=query,
            seed_limit=settings.seed_limit,
            result_limit=settings.limit,
            neighbor_depth=settings.neighbor_depth,
            include_section_references=settings.include_section_references,
            section_max_children=settings.section_max_children,
            include_keyword_matches=settings.include_keyword_matches,
            keyword_overlap_min=settings.keyword_overlap_min,
            keyword_overlap_ratio_min=settings.keyword_overlap_ratio_min,
            include_similarity_matches=settings.include_similarity_matches,
            similarity_threshold=settings.similarity_threshold,
        )

        data[f"{self.id}.graph_hits"] = [hit.model_dump() if hasattr(hit, "model_dump") else dict(hit) for hit in hits]
        logger.info(
            "GraphRetriever succeeded: component_id=%s graph=%s query_chars=%d returned=%d hits=%d latency=%.2fs",
            self.id,
            settings.graph_name,
            len(query),
            len(references),
            len(hits),
            latency,
        )
        return references, latency
