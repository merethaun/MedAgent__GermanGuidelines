from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.constants.auth_config import ROLE_ADMIN, ROLE_EVALUATOR
from app.controllers.dependencies.auth_dependencies import get_current_user, require_roles
from app.controllers.http_errors import as_http_error
from app.models.auth.user import CurrentUser
from app.models.evaluation.task import ManualReviewSubmission, ManualReviewTask
from app.services.evaluation.task_service import TaskService
from app.services.service_registry import get_task_service

task_router = APIRouter()


@task_router.get(
    "/tasks",
    response_model=List[ManualReviewTask],
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def list_tasks(
        run_id: Optional[str] = Query(default=None),
        status: Optional[str] = Query(default=None),
        mine: bool = Query(default=False),
        include_open: bool = Query(default=True),
        user: CurrentUser = Depends(get_current_user),
        service: TaskService = Depends(get_task_service),
) -> List[ManualReviewTask]:
    try:
        return service.list_tasks(
            user=user,
            run_id=run_id,
            status=status,
            mine=mine,
            include_open=include_open,
        )
    except ValueError as exc:
        raise as_http_error(exc) from exc


@task_router.post(
    "/tasks/{task_id}/claim",
    response_model=ManualReviewTask,
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def claim_task(
        task_id: str,
        user: CurrentUser = Depends(get_current_user),
        service: TaskService = Depends(get_task_service),
) -> ManualReviewTask:
    try:
        return service.claim_task(task_id, user)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@task_router.post(
    "/tasks/{task_id}/submit",
    response_model=ManualReviewTask,
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_EVALUATOR))],
)
def submit_task(
        task_id: str,
        payload: ManualReviewSubmission,
        user: CurrentUser = Depends(get_current_user),
        service: TaskService = Depends(get_task_service),
) -> ManualReviewTask:
    try:
        return service.submit_task(task_id, user, payload)
    except ValueError as exc:
        raise as_http_error(exc) from exc
