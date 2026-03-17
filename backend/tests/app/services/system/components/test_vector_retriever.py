from types import SimpleNamespace

import app.services.system.components.component_registry  # noqa: F401
from app.models.system.system_chat_interaction import RetrievalResult
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
                        "guideline_id": "69b2b1ea9ced93a73a11bce0",
                        "text": "Ultrasound is preferred as an initial imaging modality.",
                        "headers": "2 Diagnostics / 2.1 Imaging",
                    },
                ),
            ],
        )


def test_resolve_component_path_for_vector_retriever():
    resolved = resolve_component_path(["retriever", "vector_retriever"])
    assert resolved is VectorRetriever


def test_vector_retriever_maps_hits_to_retrieval_results(monkeypatch):
    monkeypatch.setattr(
        "app.services.system.components.retriever.vector_retriever.get_weaviate_vector_store_service",
        lambda: _FakeVectorStoreService(),
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
            },
        },
        variant="vector_retriever",
    )
    
    data, next_component_id = retriever.execute({"start.current_user_input": "appendicitis"})
    
    assert next_component_id == ""
    assert "retriever.latency" in data
    assert data["retriever.references"] == [
        RetrievalResult(
            reference_id="69b2b1ea9ced93a73a11bcde",
            source_id="69b2b1ea9ced93a73a11bcdf",
            retrieval="Suspected appendicitis should be evaluated promptly.",
            weaviate_uuid="hit-1",
            weaviate_score=0.93,
            weaviate_distance=0.07,
            weaviate_properties={
                "reference_id": "69b2b1ea9ced93a73a11bcde",
                "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                "text": "Suspected appendicitis should be evaluated promptly.",
                "headers": "1 Acute abdomen / 1.1 Appendicitis",
            },
        ),
        RetrievalResult(
            source_id="69b2b1ea9ced93a73a11bce0",
            retrieval="Ultrasound is preferred as an initial imaging modality.",
            weaviate_uuid="hit-2",
            weaviate_score=0.82,
            weaviate_distance=0.18,
            weaviate_properties={
                "guideline_id": "69b2b1ea9ced93a73a11bce0",
                "text": "Ultrasound is preferred as an initial imaging modality.",
                "headers": "2 Diagnostics / 2.1 Imaging",
            },
        ),
    ]


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
                                "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                                "text": "Primary result from text search.",
                            },
                        ),
                        SimpleNamespace(
                            uuid="hit-2",
                            score=0.5,
                            properties={
                                "reference_id": "69b2b1ea9ced93a73a11bce1",
                                "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                                "text": "Secondary text result.",
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
                            "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                            "text": "Primary result from text search.",
                        },
                    ),
                ],
            )
    
    monkeypatch.setattr(
        "app.services.system.components.retriever.vector_retriever.get_weaviate_vector_store_service",
        lambda: FakeVectorStoreService(),
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
    assert [str(item.reference_id) if item.reference_id else None for item in data["retriever.references"]] == [
        "69b2b1ea9ced93a73a11bcde",
        "69b2b1ea9ced93a73a11bce1",
    ]
    assert data["retriever.references"][0].weaviate_uuid == "hit-1"
    assert data["retriever.references"][0].weaviate_score == 0.8
    assert data["retriever.references"][0].weaviate_properties == {
        "reference_id": "69b2b1ea9ced93a73a11bcde",
        "guideline_id": "69b2b1ea9ced93a73a11bcdf",
        "text": "Primary result from text search.",
    }
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
