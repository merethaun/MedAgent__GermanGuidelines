import app.services.system.components.component_registry  # noqa: F401
from bson import ObjectId

from app.models.knowledge.guideline.guideline_reference import GuidelineTextReference
from app.services.system.components.structure.list_component import ListComponent
from app.services.system.components.structure.merge_component import MergeComponent
from app.utils.system.resolve_component_path import resolve_component_path


def test_resolve_component_path_for_structure_components():
    assert resolve_component_path(["list"]) is ListComponent
    assert resolve_component_path(["merge"]) is MergeComponent


def test_list_component_executes_child_component_for_each_item(monkeypatch):
    references_by_query = {
        "appendizitis diagnostik": [
            GuidelineTextReference(
                _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
                guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                contained_text="Labor und Sonographie helfen bei der Diagnostik.",
            ),
        ],
        "appendizitis therapie": [
            GuidelineTextReference(
                _id=ObjectId("69b2b1ea9ced93a73a11bce0"),
                guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                contained_text="Die Therapie richtet sich nach dem klinischen Befund.",
            ),
        ],
    }

    class FakeVectorStoreService:
        def search(self, collection_name, request):
            result = references_by_query[request.query][0]
            return type(
                "Response",
                (),
                {
                    "hits": [
                        type(
                            "Hit",
                            (),
                            {
                                "uuid": str(result.id),
                                "score": 0.9,
                                "distance": 0.1,
                                "properties": {"reference_id": str(result.id)},
                            },
                        )(),
                    ],
                },
            )()

    class FakeGuidelineReferenceService:
        def get_reference_by_id(self, reference_id):
            for references in references_by_query.values():
                for reference in references:
                    if str(reference.id) == str(reference_id):
                        return reference
            raise AssertionError("Unexpected reference_id")

    monkeypatch.setattr(
        "app.services.system.components.retriever.vector_retriever.get_weaviate_vector_store_service",
        lambda: FakeVectorStoreService(),
    )
    monkeypatch.setattr(
        "app.services.system.components.retriever.vector_retriever.get_guideline_reference_service",
        lambda: FakeGuidelineReferenceService(),
    )

    component = ListComponent(
        component_id="retrieve_each",
        name="Retrieve each",
        parameters={
            "list": "{query_aug.subqueries}",
            "component_template": {
                "component_id": "single_retriever",
                "name": "Retriever",
                "type": "retriever/vector_retriever",
                "parameters": {
                    "query": "<list_value>",
                    "settings": {
                        "weaviate_collection": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
                        "vector_name": "text",
                        "limit": 3,
                    },
                },
            },
        },
        variant="list",
    )

    data, next_component_id = component.execute(
        {"query_aug.subqueries": ["appendizitis diagnostik", "appendizitis therapie"]},
    )

    assert next_component_id == ""
    assert data["retrieve_each.items"] == ["appendizitis diagnostik", "appendizitis therapie"]
    assert len(data["retrieve_each.component_outputs"]) == 2
    assert data["retrieve_each.component_outputs"][0]["list_item"] == "appendizitis diagnostik"
    assert len(data["retrieve_each.component_outputs"][0]["references"]) == 1
    assert data["retrieve_each.component_outputs"][1]["references"][0].extract_content().startswith("Die Therapie")


def test_merge_component_flattens_and_deduplicates_references():
    duplicate_reference = GuidelineTextReference(
        _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
        guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
        contained_text="Labor und Sonographie helfen bei der Diagnostik.",
    )
    distinct_reference = GuidelineTextReference(
        _id=ObjectId("69b2b1ea9ced93a73a11bce0"),
        guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
        contained_text="Die Therapie richtet sich nach dem klinischen Befund.",
    )

    component = MergeComponent(
        component_id="merge",
        name="Merge",
        parameters={
            "items": "{retrieve_each.component_outputs}",
            "item_key": "references",
            "latency_key": "latency",
        },
        variant="merge",
    )

    data, next_component_id = component.execute(
        {
            "retrieve_each.component_outputs": [
                {"references": [duplicate_reference], "latency": 0.4},
                {"references": [duplicate_reference, distinct_reference], "latency": 0.6},
            ],
        },
    )

    assert next_component_id == ""
    assert data["merge.total_input_items"] == 3
    assert data["merge.merged_count"] == 2
    assert data["merge.references"] == [duplicate_reference, distinct_reference]
    assert data["merge.latency"] == 1.0
