import app.services.system.components.component_registry  # noqa: F401
from bson import ObjectId

from app.models.knowledge.guideline.guideline_reference import GuidelineHierarchyEntry, GuidelineTextReference
from app.services.system.components.expander.reference_expander import (
    HierarchyReferencesExpander,
    NeighborhoodReferencesExpander,
)
from app.utils.system.resolve_component_path import resolve_component_path


def _make_reference(reference_id: str, text: str, order: int, title: str = "Appendicitis"):
    return GuidelineTextReference(
        _id=ObjectId(reference_id),
        guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
        contained_text=text,
        document_hierarchy=[
            GuidelineHierarchyEntry(title="Acute abdomen", heading_level=1, heading_number="1", order=10),
            GuidelineHierarchyEntry(title=title, heading_level=2, heading_number="1.1", order=order),
        ],
    )


def test_resolve_component_paths_for_expanders():
    assert resolve_component_path(["expander", "neighborhood_references"]) is NeighborhoodReferencesExpander
    assert resolve_component_path(["expander", "hierarchy_references"]) is HierarchyReferencesExpander


def test_neighborhood_expander_adds_adjacent_chunks(monkeypatch):
    seed = _make_reference("69b2b1ea9ced93a73a11bcde", "Seed chunk", 11)
    previous = _make_reference("69b2b1ea9ced93a73a11bce0", "Previous chunk", 10)
    following = _make_reference("69b2b1ea9ced93a73a11bce1", "Following chunk", 12)

    class FakeExpanderService:
        def expand_references(self, request):
            assert request.settings.kind.value == "neighborhood"
            return type(
                "Response",
                (),
                {
                    "references": [seed, previous, following],
                    "added_references": [previous, following],
                    "latency": 0.02,
                },
            )()

    monkeypatch.setattr(
        "app.services.system.components.expander.reference_expander.get_guideline_expander_service",
        lambda: FakeExpanderService(),
    )

    component = NeighborhoodReferencesExpander(
        component_id="expand",
        name="Neighborhood expander",
        parameters={
            "references_key": "retriever.references",
            "settings": {
                "kind": "neighborhood",
                "context_window_size": 1,
                "direction": "both",
            },
        },
        variant="neighborhood_references",
    )

    data, next_component_id = component.execute({"retriever.references": [seed]})

    assert next_component_id == ""
    assert [reference.extract_content() for reference in data["expand.references"]] == [
        "Seed chunk",
        "Previous chunk",
        "Following chunk",
    ]
    assert [reference.extract_content() for reference in data["expand.added_references"]] == [
        "Previous chunk",
        "Following chunk",
    ]


def test_hierarchy_expander_adds_section_references(monkeypatch):
    seed = _make_reference("69b2b1ea9ced93a73a11bcde", "Seed chunk", 11)
    sibling = _make_reference("69b2b1ea9ced93a73a11bce0", "Sibling chunk", 12)

    class FakeExpanderService:
        def expand_references(self, request):
            assert request.settings.kind.value == "hierarchy"
            return type(
                "Response",
                (),
                {
                    "references": [seed, sibling],
                    "added_references": [sibling],
                    "latency": 0.01,
                },
            )()

    monkeypatch.setattr(
        "app.services.system.components.expander.reference_expander.get_guideline_expander_service",
        lambda: FakeExpanderService(),
    )

    component = HierarchyReferencesExpander(
        component_id="hierarchy_expand",
        name="Hierarchy expander",
        parameters={
            "references_key": "cross_encoder.references",
            "settings": {
                "kind": "hierarchy",
                "mode": "direct_parent",
            },
        },
        variant="hierarchy_references",
    )

    data, next_component_id = component.execute({"cross_encoder.references": [seed]})

    assert next_component_id == ""
    assert [reference.extract_content() for reference in data["hierarchy_expand.references"]] == [
        "Seed chunk",
        "Sibling chunk",
    ]
    assert [reference.extract_content() for reference in data["hierarchy_expand.added_references"]] == ["Sibling chunk"]
