from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.constants.auth_config import ROLE_ADMIN, ROLE_USER
from app.controllers.dependencies.auth_dependencies import require_roles
from app.exceptions.knowledge.guideline import GuidelineNotFoundError, TextInGuidelineNotFoundError
from app.models.knowledge.guideline import BoundingBox, GuidelineEntry, GuidelineReference, GuidelineReferenceGroup, ReferenceType
from app.models.knowledge.guideline.bounding_box_finder_api import BoundingBoxFinderRequest
from app.services.knowledge.guideline import BoundingBoxFinderService, GuidelineReferenceService, GuidelineService
from app.services.service_registry import get_bounding_box_finder_service, get_guideline_reference_service, get_guideline_service

guideline_reference_router = APIRouter()


# ============================================================
# Reference Groups
# ============================================================

@guideline_reference_router.post(
    "/groups",
    response_model=str,
    status_code=status.HTTP_201_CREATED,
    summary="Create a guideline reference group (admin only)",
    description="Stores a new GuidelineReferenceGroup in MongoDB and returns its MongoDB id.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_reference_group(
        reference_group: GuidelineReferenceGroup,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> str:
    try:
        created = service.create_reference_group(reference_group)
        return str(created.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.get(
    "/groups",
    response_model=List[GuidelineReferenceGroup],
    summary="List guideline reference groups (admin + study_user)",
    description="Returns all reference groups from MongoDB.",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def list_reference_groups(
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> List[GuidelineReferenceGroup]:
    try:
        return service.list_reference_groups()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.get(
    "/groups/{reference_group_id}",
    response_model=GuidelineReferenceGroup,
    summary="Get a reference group by id (admin + study_user)",
    description="Fetches a single reference group by MongoDB id.",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def get_reference_group(
        reference_group_id: str,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReferenceGroup:
    try:
        return service.get_reference_group_by_id(reference_group_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@guideline_reference_router.put(
    "/groups/{reference_group_id}",
    response_model=GuidelineReferenceGroup,
    summary="Update a reference group (admin only)",
    description="Updates a reference group document in MongoDB (partial update semantics).",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def update_reference_group(
        reference_group_id: str,
        reference_group: GuidelineReferenceGroup,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReferenceGroup:
    try:
        return service.update_reference_group(reference_group_id, reference_group)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.delete(
    "/groups/{reference_group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a reference group (admin only)",
    description="Deletes a reference group document from MongoDB.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_reference_group(
        reference_group_id: str,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> None:
    try:
        service.delete_reference_group_by_id(reference_group_id)
        return None
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# References
# ============================================================


@guideline_reference_router.post(
    "/finder",
    response_model=List[BoundingBox],
    status_code=status.HTTP_200_OK,
    summary="In a guideline, find the bounding boxes matching the text",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def find_bounding_boxes(
        bounding_box_request: BoundingBoxFinderRequest,
        service: BoundingBoxFinderService = Depends(get_bounding_box_finder_service),
        guideline_service: GuidelineService = Depends(get_guideline_service),
) -> List[BoundingBox]:
    try:
        guideline: GuidelineEntry = guideline_service.get_guideline_by_id(bounding_box_request.guideline_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    try:
        return service.text_to_bounding_boxes(
            guideline, bounding_box_request.text, start_page=bounding_box_request.start_page, end_page=bounding_box_request.end_page,
        )
    except TextInGuidelineNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@guideline_reference_router.get(
    "/finder/text",
    response_model=str,
    status_code=status.HTTP_200_OK,
    summary="For a specific guideline page, get all the contained text",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def get_text_from_guideline_page(
        guideline_id: str,
        page_number: int,
        service: BoundingBoxFinderService = Depends(get_bounding_box_finder_service),
        guideline_service: GuidelineService = Depends(get_guideline_service),
) -> str:
    try:
        guideline: GuidelineEntry = guideline_service.get_guideline_by_id(guideline_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    try:
        return service.get_page_text(guideline, page_number)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@guideline_reference_router.post(
    "/",
    response_model=str,
    status_code=status.HTTP_201_CREATED,
    summary="Create a guideline reference (admin only)",
    description="Stores a new GuidelineReference (polymorphic) in MongoDB and returns its MongoDB id.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_reference(
        reference: GuidelineReference,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> str:
    try:
        created = service.create_reference(reference)
        return str(created.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.get(
    "/",
    response_model=List[GuidelineReference],
    summary="List guideline references (admin + study_user)",
    description="Returns references from MongoDB with optional filters.",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def list_references(
        reference_group_id: Optional[str] = Query(None, description="Filter by reference group id"),
        guideline_id: Optional[str] = Query(None, description="Filter by guideline id"),
        reference_type: Optional[ReferenceType] = Query(None, description="Filter by reference type"),
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> List[GuidelineReference]:
    try:
        return service.list_references(
            reference_group_id=reference_group_id,
            guideline_id=guideline_id,
            reference_type=reference_type,
        )
    except GuidelineNotFoundError as e:
        # e.g., invalid ObjectId in filters
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.get(
    "/{reference_id}",
    response_model=GuidelineReference,
    summary="Get a guideline reference by id (admin + study_user)",
    description="Fetches a single guideline reference by MongoDB id.",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def get_reference(
        reference_id: str,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReference:
    try:
        return service.get_reference_by_id(reference_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        # unknown reference type (if your service raises ValueError for that)
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.put(
    "/{reference_id}",
    response_model=GuidelineReference,
    summary="Update a guideline reference (admin only)",
    description="Updates a guideline reference in MongoDB (partial update semantics when fields are unset).",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def update_reference(
        reference_id: str,
        reference: GuidelineReference,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReference:
    try:
        return service.update_reference(reference_id, reference)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.patch(
    "/{reference_id}",
    response_model=GuidelineReference,
    summary="Patch a guideline reference (admin only)",
    description="Partially updates a guideline reference using a JSON object of fields to set.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def patch_reference(
        reference_id: str,
        patch: Dict = Body(..., description="Fields to update (MongoDB $set)"),
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReference:
    try:
        return service.update_reference(reference_id, patch)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.delete(
    "/{reference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a guideline reference (admin only)",
    description="Deletes a guideline reference document from MongoDB.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_reference(
        reference_id: str,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> None:
    try:
        service.delete_reference_by_id(reference_id)
        return None
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# Bulk deletes (optional but often useful)
# ============================================================

@guideline_reference_router.delete(
    "/by-guideline/{guideline_id}",
    response_model=Dict,
    summary="Delete all references for a guideline (admin only)",
    description="Deletes all references linked to a guideline_id and returns count + deleted ids.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_references_by_guideline(
        guideline_id: str,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> Dict:
    try:
        deleted_count, deleted_ids = service.delete_references_by_guideline_id(guideline_id)
        return {"deleted_count": deleted_count, "deleted_ids": deleted_ids}
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@guideline_reference_router.delete(
    "/by-group/{reference_group_id}",
    response_model=Dict,
    summary="Delete all references for a reference group (admin only)",
    description="Deletes all references linked to a reference_group_id and returns count + deleted ids.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_references_by_group(
        reference_group_id: str,
        service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> Dict:
    try:
        deleted_count, deleted_ids = service.delete_references_by_reference_group_id(reference_group_id)
        return {"deleted_count": deleted_count, "deleted_ids": deleted_ids}
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
