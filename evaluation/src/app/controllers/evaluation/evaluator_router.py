from typing import List

from fastapi import APIRouter, Depends

from app.constants.auth_config import ROLE_ADMIN, ROLE_EVALUATOR
from app.controllers.dependencies.auth_dependencies import get_current_user, require_roles
from app.controllers.http_errors import as_http_error
from app.models.auth.user import CurrentUser
from app.models.evaluation.evaluator import EvaluatorProfile
from app.services.evaluation.evaluator_profile_service import EvaluatorProfileService
from app.services.service_registry import get_evaluator_profile_service

evaluator_router = APIRouter()


@evaluator_router.post(
    "/evaluators/me/register",
    response_model=EvaluatorProfile,
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def register_evaluator(
        user: CurrentUser = Depends(get_current_user),
        service: EvaluatorProfileService = Depends(get_evaluator_profile_service),
) -> EvaluatorProfile:
    try:
        return service.upsert_from_user(user)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@evaluator_router.get(
    "/evaluators",
    response_model=List[EvaluatorProfile],
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def list_evaluators(service: EvaluatorProfileService = Depends(get_evaluator_profile_service)) -> List[EvaluatorProfile]:
    try:
        return service.list_profiles()
    except ValueError as exc:
        raise as_http_error(exc) from exc
