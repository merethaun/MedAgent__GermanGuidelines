from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import get_access_token, require_roles
from app.controllers.http_errors import as_http_error
from app.models.evaluation.dataset import QuestionEntry, QuestionGroup
from app.services.evaluation.dataset_service import DatasetService
from app.services.service_registry import get_dataset_service

dataset_router = APIRouter()


@dataset_router.post(
    "/question-groups",
    response_model=QuestionGroup,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_question_group(
        payload: QuestionGroup,
        service: DatasetService = Depends(get_dataset_service),
) -> QuestionGroup:
    try:
        return service.create_question_group(payload)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@dataset_router.get(
    "/question-groups",
    response_model=List[QuestionGroup],
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def list_question_groups(service: DatasetService = Depends(get_dataset_service)) -> List[QuestionGroup]:
    return service.list_question_groups()


@dataset_router.post(
    "/questions",
    response_model=QuestionEntry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_question(
        payload: QuestionEntry,
        service: DatasetService = Depends(get_dataset_service),
) -> QuestionEntry:
    try:
        return service.create_question(payload)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@dataset_router.get(
    "/questions",
    response_model=List[QuestionEntry],
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def list_questions(
        question_group_id: Optional[str] = Query(default=None),
        question: Optional[str] = Query(default=None),
        super_class: Optional[str] = Query(default=None),
        sub_class: Optional[str] = Query(default=None),
        service: DatasetService = Depends(get_dataset_service),
) -> List[QuestionEntry]:
    try:
        return service.list_questions(
            question_group_id=question_group_id,
            question=question,
            super_class=super_class,
            sub_class=sub_class,
        )
    except ValueError as exc:
        raise as_http_error(exc) from exc


@dataset_router.put(
    "/questions/{question_id}",
    response_model=QuestionEntry,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def update_question(
        question_id: str,
        payload: QuestionEntry,
        service: DatasetService = Depends(get_dataset_service),
) -> QuestionEntry:
    try:
        return service.update_question(question_id, payload)
    except ValueError as exc:
        raise as_http_error(exc) from exc


@dataset_router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_question(
        question_id: str,
        service: DatasetService = Depends(get_dataset_service),
) -> None:
    try:
        service.delete_question(question_id)
    except ValueError as exc:
        raise as_http_error(exc) from exc
    return None


@dataset_router.post(
    "/questions/import",
    response_model=List[QuestionEntry],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
async def import_questions(
        question_group_id: str = Query(...),
        csv_file: UploadFile = File(...),
        access_token: str = Depends(get_access_token),
        service: DatasetService = Depends(get_dataset_service),
) -> List[QuestionEntry]:
    try:
        content = await csv_file.read()
        return service.import_questions_from_csv(question_group_id, content, access_token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await csv_file.close()


@dataset_router.get(
    "/questions/export.csv",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def export_questions_csv(
        question_group_id: Optional[str] = Query(default=None),
        service: DatasetService = Depends(get_dataset_service),
) -> Response:
    try:
        csv_text = service.export_questions_to_csv(question_group_id=question_group_id)
    except ValueError as exc:
        raise as_http_error(exc) from exc
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evaluation_questions.csv"},
    )
