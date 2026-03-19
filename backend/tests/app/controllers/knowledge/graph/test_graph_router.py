from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

from app.constants.auth_config import ROLE_USER
from app.controllers.dependencies.auth_dependencies import get_current_user
from app.controllers.knowledge.graph.graph_router import graph_router
from app.exceptions.knowledge.graph import GraphNotFoundError
from app.models.auth.user import CurrentUser
from app.models.knowledge.graph import GraphSearchHit, GraphSearchReason
from app.models.knowledge.guideline.guideline_reference import GuidelineTextReference
from app.services.service_registry import get_graph_service


class _FakeGraphService:
    def expand_from_references(self, **kwargs):
        assert kwargs["graph_name"] == "guideline_graph_v1"
        assert len(kwargs["seed_references"]) == 1
        assert kwargs["include_seed_references"] is True
        return (
            [
                GuidelineTextReference(
                    _id=ObjectId("69b2b1ea9ced93a73a11bcde"),
                    guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                    contained_text="Ultrasound is preferred during pregnancy when appendicitis is suspected.",
                ),
            ],
            [
                GuidelineTextReference(
                    _id=ObjectId("69b2b1ea9ced93a73a11bce0"),
                    guideline_id=ObjectId("69b2b1ea9ced93a73a11bcdf"),
                    contained_text="MRI can be considered when ultrasound is inconclusive.",
                ),
            ],
            [
                GraphSearchHit(
                    reference_id="69b2b1ea9ced93a73a11bcde",
                    score=2.1,
                    heading_path="Diagnostics > Pregnancy",
                    guideline_id="69b2b1ea9ced93a73a11bcdf",
                    reasons=[
                        GraphSearchReason(kind="seed", score=1.4, detail="Matched the Neo4j fulltext reference index."),
                    ],
                ),
            ],
            0.12,
        )


class _MissingGraphService:
    def expand_from_references(self, **kwargs):
        raise GraphNotFoundError(kwargs["graph_name"])


def test_graph_retrieve_endpoint_returns_references_and_hits():
    app = FastAPI()
    app.include_router(graph_router, prefix="/graph/neo4j")
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(sub="user-1", username="m", roles={ROLE_USER})
    app.dependency_overrides[get_graph_service] = lambda: _FakeGraphService()

    client = TestClient(app)
    response = client.post(
        "/graph/neo4j/retrieve",
        json={
            "references": [
                {
                    "_id": "69b2b1ea9ced93a73a11bcde",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                    "type": "text",
                    "contained_text": "Ultrasound is preferred during pregnancy when appendicitis is suspected."
                }
            ],
            "settings": {
                "graph_name": "guideline_graph_v1",
                "limit": 5,
                "include_seed_references": True,
                "neighbor_depth": 1,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["latency"] == 0.12
    assert payload["graph_hits"][0]["reference_id"] == "69b2b1ea9ced93a73a11bcde"
    assert payload["references"][0]["contained_text"] == "Ultrasound is preferred during pregnancy when appendicitis is suspected."
    assert payload["added_references"][0]["contained_text"] == "MRI can be considered when ultrasound is inconclusive."

    app.dependency_overrides.clear()


def test_graph_retrieve_endpoint_returns_404_for_missing_graph():
    app = FastAPI()
    app.include_router(graph_router, prefix="/graph/neo4j")
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(sub="user-1", username="m", roles={ROLE_USER})
    app.dependency_overrides[get_graph_service] = lambda: _MissingGraphService()

    client = TestClient(app)
    response = client.post(
        "/graph/neo4j/retrieve",
        json={
            "references": [
                {
                    "_id": "69b2b1ea9ced93a73a11bcde",
                    "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                    "type": "text",
                    "contained_text": "Ultrasound is preferred during pregnancy when appendicitis is suspected."
                }
            ],
            "settings": {
                "graph_name": "missing_graph",
                "limit": 5,
                "include_seed_references": True,
                "neighbor_depth": 1,
            },
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Graph 'missing_graph' does not exist."

    app.dependency_overrides.clear()
