from bson import ObjectId

from app.models.knowledge.guideline.guideline_reference import GuidelineTextReference
from app.services.system.components.retriever.graph_retriever import GraphRetriever


class _FakeGraphService:
    def retrieve_references(self, **kwargs):
        assert kwargs["graph_name"] == "guideline_graph_v1"
        assert kwargs["query"] == "appendicitis pregnancy"
        assert kwargs["seed_limit"] == 4
        return (
            [
                GuidelineTextReference(
                    _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
                    guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                    contained_text="Ultrasound is preferred during pregnancy when appendicitis is suspected.",
                ),
            ],
            [
                {
                    "reference_id": "69b2b1ea9ced93a73a11bcde",
                    "score": 2.1,
                    "heading_path": "Diagnostics > Pregnancy",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                    "reasons": [
                        {"kind": "seed", "score": 1.4, "detail": "Matched the Neo4j fulltext reference index."},
                        {"kind": "section", "score": 0.7, "detail": "Shares the section 'Diagnostics > Pregnancy' with a seed reference."},
                    ],
                },
            ],
            0.01,
        )

def test_graph_retriever_returns_guideline_references_and_graph_hits(monkeypatch):
    monkeypatch.setattr(
        "app.services.system.components.retriever.graph_retriever.get_graph_service",
        lambda: _FakeGraphService(),
    )

    retriever = GraphRetriever(
        component_id="retriever",
        name="Graph retriever",
        parameters={
            "query": "{start.current_user_input}",
            "settings": {
                "graph_name": "guideline_graph_v1",
                "limit": 5,
                "seed_limit": 4,
                "neighbor_depth": 1,
            },
        },
        variant="graph_retriever",
    )

    data, next_component_id = retriever.execute({"start.current_user_input": "appendicitis pregnancy"})

    assert next_component_id == ""
    assert "retriever.latency" in data
    assert len(data["retriever.references"]) == 1
    assert data["retriever.references"][0].extract_content() == "Ultrasound is preferred during pregnancy when appendicitis is suspected."
    assert data["retriever.graph_hits"][0]["reference_id"] == "69b2b1ea9ced93a73a11bcde"
    assert data["retriever.graph_hits"][0]["reasons"][0]["kind"] == "seed"
