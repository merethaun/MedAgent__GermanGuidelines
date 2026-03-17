import app.services.system.components.component_registry  # noqa: F401
from bson import ObjectId

from app.models.knowledge.guideline.guideline_reference import GuidelineHierarchyEntry, GuidelineTextReference
from app.services.system.components.filter.guideline_context_filter import DeduplicateReferencesFilter, RelevanceFilterReferences
from app.utils.system.resolve_component_path import resolve_component_path


class _FakeGuidelineContextFilterService:
    def __init__(self):
        self.requests = []

    def deduplicate_references(self, request):
        self.requests.append(request)
        return type(
            "Response",
            (),
            {
                "kept_references": [request.references[0]],
                "dropped_references": request.references[1:],
                "decisions": [
                    type("Decision", (), {"model_dump": lambda self: {"index": 0, "kept": True}})(),
                    type("Decision", (), {"model_dump": lambda self: {"index": 1, "kept": False}})(),
                ],
                "filter_input": request.filter_input,
                "latency": 0.05,
            },
        )()


def test_resolve_component_paths_for_guideline_context_filters():
    assert resolve_component_path(["filter", "deduplicate_references"]) is DeduplicateReferencesFilter
    assert resolve_component_path(["filter", "relevance_filter_references"]) is RelevanceFilterReferences


def test_deduplicate_references_component_filters_references(monkeypatch):
    fake_service = _FakeGuidelineContextFilterService()
    monkeypatch.setattr(
        "app.services.system.components.filter.guideline_context_filter.get_guideline_context_filter_service",
        lambda: fake_service,
    )

    component = DeduplicateReferencesFilter(
        component_id="post_filter",
        name="Deduplicate references",
        parameters={
            "references_key": "retriever.references",
            "filter_input": "{start.current_user_input}",
            "settings": {
                "kind": "deduplicate",
                "method": "score",
                "keep_top_k": 1,
                "score_field": "document_hierarchy.0.order",
                "properties": [
                    {"path": "content", "label": "text"},
                    {"path": "heading_path", "label": "section"},
                ],
            },
        },
        variant="deduplicate_references",
    )

    references = [
        GuidelineTextReference(
            _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text="Appendicitis should be evaluated promptly.",
            document_hierarchy=[GuidelineHierarchyEntry(title="Appendicitis", heading_level=1, heading_number="1.1", order=91)],
        ),
        GuidelineTextReference(
            _id=ObjectId("69b2b1ea9ced93a73a11bce0"),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text="Gallstones may present differently.",
            document_hierarchy=[GuidelineHierarchyEntry(title="Gallstones", heading_level=1, heading_number="4.2", order=42)],
        ),
    ]

    data, next_component_id = component.execute(
        {
            "start.current_user_input": "appendicitis diagnostics",
            "retriever.references": references,
        },
    )

    assert next_component_id == ""
    assert data["post_filter.references"] == [references[0]]
    assert data["post_filter.dropped_references"] == [references[1]]
    assert data["post_filter.filter_input"] == "appendicitis diagnostics"
    assert data["post_filter.latency"] == 0.05
    assert fake_service.requests[0].settings.properties[1].path == "heading_path"
