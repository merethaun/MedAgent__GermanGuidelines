from types import SimpleNamespace

import app.services.system.components.component_registry  # noqa: F401
from bson import ObjectId

from app.models.knowledge.guideline.guideline_reference import GuidelineHierarchyEntry, GuidelineTextReference
from app.services.system.components.retriever.vector_retriever import MultiQueriesVectorRetriever, VectorRetriever
from app.utils.system.resolve_component_path import resolve_component_path


class _FakeVectorStoreService:
    def search(self, collection_name, request):
        assert collection_name == "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec"
        assert request.query == "appendicitis"
        assert request.vector_name == "text"
        return SimpleNamespace(
            hits=[
                SimpleNamespace(
                    uuid="hit-1",
                    score=0.93,
                    distance=0.07,
                    properties={
                        "reference_id": "69b2b1ea9ced93a73a11bcde",
                        "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                        "text": "Suspected appendicitis should be evaluated promptly.",
                        "headers": "1 Acute abdomen / 1.1 Appendicitis",
                    },
                ),
                SimpleNamespace(
                    uuid="hit-2",
                    score=0.82,
                    distance=0.18,
                    properties={
                        "contained_reference": {
                            "_id": "69b2b1ea9ced93a73a11bce0",
                            "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                            "type": "text",
                            "contained_text": "Ultrasound is preferred as an initial imaging modality.",
                            "document_hierarchy": [
                                {
                                    "title": "Diagnostics",
                                    "heading_level": 1,
                                    "heading_number": "2.1",
                                    "order": 21,
                                },
                            ],
                        },
                    },
                ),
            ],
        )


class _FakeGuidelineReferenceService:
    def get_reference_by_id(self, reference_id):
        assert str(reference_id) == "69b2b1ea9ced93a73a11bcde"
        return GuidelineTextReference(
            _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
            guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
            contained_text="Suspected appendicitis should be evaluated promptly.",
            document_hierarchy=[
                GuidelineHierarchyEntry(
                    title="Appendicitis",
                    heading_level=1,
                    heading_number="1.1",
                    order=11,
                ),
            ],
        )


def test_resolve_component_path_for_vector_retriever():
    resolved = resolve_component_path(["retriever", "vector_retriever"])
    assert resolved is VectorRetriever


def test_vector_retriever_maps_hits_to_guideline_references(monkeypatch):
    monkeypatch.setattr(
        "app.services.system.components.retriever.vector_retriever.get_weaviate_vector_store_service",
        lambda: _FakeVectorStoreService(),
    )
    monkeypatch.setattr(
        "app.services.system.components.retriever.vector_retriever.get_guideline_reference_service",
        lambda: _FakeGuidelineReferenceService(),
    )

    retriever = VectorRetriever(
        component_id="retriever",
        name="Vector retriever",
        parameters={
            "query": "{start.current_user_input}",
            "settings": {
                "weaviate_collection": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
                "vector_name": "text",
                "limit": 3,
                "contained_reference_property": "contained_reference",
            },
        },
        variant="vector_retriever",
    )

    data, next_component_id = retriever.execute({"start.current_user_input": "appendicitis"})

    assert next_component_id == ""
    assert "retriever.latency" in data
    assert [str(item.id) for item in data["retriever.references"]] == [
        "69b2b1ea9ced93a73a11bcde",
        "69b2b1ea9ced93a73a11bce0",
    ]
    assert all(isinstance(item, GuidelineTextReference) for item in data["retriever.references"])
    assert data["retriever.references"][1].extract_content() == "Ultrasound is preferred as an initial imaging modality."


def test_resolve_component_path_for_multi_queries_vector_retriever():
    resolved = resolve_component_path(["retriever", "multi_queries_vector_retriever"])
    assert resolved is MultiQueriesVectorRetriever


def test_multi_queries_vector_retriever_merges_weighted_hits(monkeypatch):
    seen_requests = []

    class FakeVectorStoreService:
        def search(self, collection_name, request):
            assert collection_name == "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec"
            seen_requests.append(request)
            if request.vector_name == "text":
                return SimpleNamespace(
                    hits=[
                        SimpleNamespace(
                            uuid="hit-1",
                            score=0.8,
                            properties={
                                "reference_id": "69b2b1ea9ced93a73a11bcde",
                            },
                        ),
                        SimpleNamespace(
                            uuid="hit-2",
                            score=0.5,
                            properties={
                                "reference_id": "69b2b1ea9ced93a73a11bce1",
                            },
                        ),
                    ],
                )

            return SimpleNamespace(
                hits=[
                    SimpleNamespace(
                        uuid="hit-3",
                        score=0.6,
                        properties={
                            "reference_id": "69b2b1ea9ced93a73a11bcde",
                        },
                    ),
                ],
            )

    class FakeGuidelineReferenceService:
        def get_reference_by_id(self, reference_id):
            texts = {
                "69b2b1ea9ced93a73a11bcde": "Primary result from text search.",
                "69b2b1ea9ced93a73a11bce1": "Secondary text result.",
            }
            return GuidelineTextReference(
                _id=ObjectId(str(reference_id)),
                guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                contained_text=texts[str(reference_id)],
            )

    monkeypatch.setattr(
        "app.services.system.components.retriever.vector_retriever.get_weaviate_vector_store_service",
        lambda: FakeVectorStoreService(),
    )
    monkeypatch.setattr(
        "app.services.system.components.retriever.vector_retriever.get_guideline_reference_service",
        lambda: FakeGuidelineReferenceService(),
    )

    retriever = MultiQueriesVectorRetriever(
        component_id="retriever",
        name="Multi query vector retriever",
        parameters={
            "settings": {
                "weaviate_collection": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
                "limit": 2,
                "queries": [
                    {"query": "{start.current_user_input}", "vector_name": "text", "weight": 1.0},
                    {"query": "{start.current_user_input}", "vector_name": "headers", "weight": 0.5},
                    {"mode": "hybrid", "keyword_properties": ["text", "headers"], "alpha": 0.2},
                ],
            },
        },
        variant="multi_queries_vector_retriever",
    )

    data, next_component_id = retriever.execute({"start.current_user_input": "appendicitis"})

    assert next_component_id == ""
    assert [str(item.id) if item.id else None for item in data["retriever.references"]] == [
        "69b2b1ea9ced93a73a11bcde",
        "69b2b1ea9ced93a73a11bce1",
    ]
    assert data["retriever.references"][0].extract_content() == "Primary result from text search."
    assert data["retriever.queries"] == [
        {"query": "appendicitis", "vector_name": "text", "weight": 1.0, "mode": "vector"},
        {"query": "appendicitis", "vector_name": "headers", "weight": 0.5, "mode": "vector"},
        {
            "query": "appendicitis",
            "vector_name": "text",
            "weight": 1.0,
            "mode": "hybrid",
        },
    ]
    assert len(seen_requests) == 3
    assert all(request.query == "appendicitis" for request in seen_requests)
