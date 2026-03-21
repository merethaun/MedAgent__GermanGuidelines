from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.constants.auth_config import ROLE_ADMIN, ROLE_EVALUATOR
from app.controllers.dependencies.auth_dependencies import get_access_token, get_current_user, require_roles
from app.controllers.http_errors import as_http_error
from app.models.auth.user import CurrentUser
from app.models.evaluation.run import EvaluationRun, EvaluationRunCreateRequest, EvaluationSample
from app.services.evaluation.run_service import RunService
from app.services.service_registry import get_run_service

run_router = APIRouter()


@run_router.post(
    "/runs",
    response_model=EvaluationRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_run(
        payload: EvaluationRunCreateRequest,
        user: CurrentUser = Depends(get_current_user),
        access_token: str = Depends(get_access_token),
        service: RunService = Depends(get_run_service),
) -> EvaluationRun:
    try:
        return service.create_run(payload, user, access_token)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@run_router.get(
    "/runs",
    response_model=List[EvaluationRun],
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def list_runs(service: RunService = Depends(get_run_service)) -> List[EvaluationRun]:
    return service.list_runs()


@run_router.get(
    "/runs/{run_id}",
    response_model=EvaluationRun,
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def get_run(
        run_id: str,
        service: RunService = Depends(get_run_service),
) -> EvaluationRun:
    try:
        return service.get_run(run_id)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@run_router.post(
    "/runs/{run_id}/rerun",
    response_model=EvaluationRun,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def rerun_run(
        run_id: str,
        access_token: str = Depends(get_access_token),
        service: RunService = Depends(get_run_service),
) -> EvaluationRun:
    try:
        return service.rerun_run(run_id, access_token)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@run_router.get(
    "/samples",
    response_model=List[EvaluationSample],
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def list_samples(
        run_id: Optional[str] = Query(default=None),
        status: Optional[str] = Query(default=None),
        service: RunService = Depends(get_run_service),
) -> List[EvaluationSample]:
    try:
        return service.list_samples(run_id=run_id, status=status)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@run_router.get(
    "/samples/{sample_id}",
    response_model=EvaluationSample,
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def get_sample(
        sample_id: str,
        service: RunService = Depends(get_run_service),
) -> EvaluationSample:
    try:
        return service.get_sample(sample_id)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@run_router.post(
    "/samples/{sample_id}/rerun",
    response_model=EvaluationSample,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def rerun_sample(
        sample_id: str,
        access_token: str = Depends(get_access_token),
        service: RunService = Depends(get_run_service),
) -> EvaluationSample:
    try:
        return service.rerun_sample(sample_id, access_token)
    except ValueError as exc:
        raise as_http_error(exc) from exc
