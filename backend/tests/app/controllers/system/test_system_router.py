from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.constants.auth_config import ROLE_USER
from app.controllers.dependencies.auth_dependencies import get_current_user
from app.controllers.system.system_router import system_router
from app.exceptions.knowledge.graph import GraphNotFoundError
from app.models.auth.user import CurrentUser
from app.services.service_registry import get_chat_service


class _MissingGraphChatService:
    def pose_question(self, chat_id, user_input):
        raise GraphNotFoundError("missing_graph")


def test_pose_question_returns_404_for_missing_graph():
    app = FastAPI()
    app.include_router(system_router, prefix="/system")
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(sub="user-1", username="m", roles={ROLE_USER})
    app.dependency_overrides[get_chat_service] = lambda: _MissingGraphChatService()

    client = TestClient(app)
    response = client.post("/system/chats/chat-1/pose", params={"user_input": "When should a wisdom tooth be removed?"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Graph 'missing_graph' does not exist."

    app.dependency_overrides.clear()
