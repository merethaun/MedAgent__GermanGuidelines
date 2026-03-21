from fastapi import APIRouter, Depends, status

from app.controllers.dependencies.auth_dependencies import get_access_token, get_current_user, require_authenticated_user
from app.controllers.http_errors import as_http_error
from app.models.auth.user import CurrentUser
from app.models.evaluation.feedback import AnswerFeedbackCreateRequest, AnswerFeedbackEntry
from app.services.evaluation.feedback_service import FeedbackService
from app.services.service_registry import get_feedback_service

feedback_router = APIRouter()


@feedback_router.post(
    "/feedback/chat-interactions",
    response_model=AnswerFeedbackEntry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_authenticated_user)],
)
def create_feedback(
        payload: AnswerFeedbackCreateRequest,
        user: CurrentUser = Depends(get_current_user),
        access_token: str = Depends(get_access_token),
        service: FeedbackService = Depends(get_feedback_service),
) -> AnswerFeedbackEntry:
    try:
        return service.create_feedback(payload, user, access_token)
    except ValueError as exc:
        raise as_http_error(exc) from exc
