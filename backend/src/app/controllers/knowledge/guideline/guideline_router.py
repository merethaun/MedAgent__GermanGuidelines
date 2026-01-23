import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.responses import FileResponse

from app.constants.auth_config import ROLE_ADMIN, ROLE_USER
from app.controllers.dependencies.auth_dependencies import require_roles
from app.exceptions.knowledge.guideline import GuidelineNotFoundError
from app.models.knowledge.guideline import GuidelineEntry
from app.services.knowledge.guideline import GuidelineService
from app.services.service_registry import get_guideline_service

guideline_router = APIRouter()


@guideline_router.post(
    "/",
    response_model=str,
    status_code=status.HTTP_201_CREATED,
    summary="Create a guideline entry (admin only)",
    description="Stores a new GuidelineEntry in MongoDB and returns its MongoDB id.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_guideline(
        guideline: GuidelineEntry,
        service: GuidelineService = Depends(get_guideline_service),
) -> str:
    try:
        created = service.create_guideline(guideline)
        return str(created.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_router.get(
    "/",
    response_model=List[GuidelineEntry],
    summary="List guideline entries (admin + study_user)",
    description="Returns all guideline entries from MongoDB (no filters yet in the simplified version).",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def list_guidelines(
        service: GuidelineService = Depends(get_guideline_service),
) -> List[GuidelineEntry]:
    try:
        return service.list_guidelines()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_router.get(
    "/{guideline_id}",
    response_model=GuidelineEntry,
    summary="Get a guideline entry by id (admin + study_user)",
    description="Fetches a single guideline entry by MongoDB id.",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def get_guideline(
        guideline_id: str,
        service: GuidelineService = Depends(get_guideline_service),
) -> GuidelineEntry:
    try:
        return service.get_guideline_by_id(guideline_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@guideline_router.put(
    "/{guideline_id}",
    response_model=GuidelineEntry,
    summary="Update a guideline entry (admin only)",
    description="Replaces the guideline entry document in MongoDB.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def update_guideline(
        guideline_id: str,
        guideline: GuidelineEntry,
        service: GuidelineService = Depends(get_guideline_service),
) -> GuidelineEntry:
    try:
        return service.update_guideline(guideline_id, guideline)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_router.delete(
    "/{guideline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a guideline entry (admin only)",
    description="Deletes the guideline entry document from MongoDB.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_guideline(
        guideline_id: str,
        service: GuidelineService = Depends(get_guideline_service),
) -> None:
    try:
        service.delete_guideline(guideline_id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@guideline_router.post(
    "/{guideline_id}/pdf/download",
    response_model=GuidelineEntry,
    summary="Download and link a guideline PDF (admin only)",
    description=(
            "Downloads a PDF from a provided URL and stores it under GUIDELINE_PDF_FOLDER "
            "(configured via env var). Updates download_information in the guideline entry if available."
    ),
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def download_guideline_pdf(
        guideline_id: str,
        url: str = Query(..., description="Public URL to the guideline PDF"),
        filename: Optional[str] = Query(
            None,
            description="Optional target filename (defaults to <awmf_register_number_full>.pdf)",
        ),
        service: GuidelineService = Depends(get_guideline_service),
) -> GuidelineEntry:
    try:
        return service.download_pdf_to_folder(guideline_id=guideline_id, url=url, filename=filename)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_router.get(
    "/{guideline_id}/pdf",
    summary="Get a guideline PDF (admin + study_user)",
    description="Returns a guideline PDF as a file attachment.",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
    response_class=FileResponse,
)
def get_guideline_pdf(
        guideline_id: str,
        service: GuidelineService = Depends(get_guideline_service),
):
    try:
        guideline = service.get_guideline_by_id(guideline_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    file_path = guideline.download_information.file_path
    if not file_path:
        raise HTTPException(status_code=404, detail="PDF not found")
    
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=os.path.basename(file_path),
    )
