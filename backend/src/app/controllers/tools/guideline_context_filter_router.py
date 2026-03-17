from fastapi import APIRouter, Depends, HTTPException, status

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import require_roles
from app.models.tools.guideline_context_filter import GuidelineContextFilterRequest, GuidelineContextFilterResponse
from app.services.service_registry import get_guideline_context_filter_service
from app.services.tools import GuidelineContextFilterService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

guideline_context_filter_router = APIRouter()


@guideline_context_filter_router.post(
    "/guideline-context-filter",
    response_model=GuidelineContextFilterResponse,
    status_code=status.HTTP_200_OK,
    summary="Filter guideline context references without a workflow (admin only)",
    description=(
        "Applies guideline context filtering to guideline reference objects. "
        "Supports two filter kinds: deduplication and relevance-based filtering."
    ),
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def guideline_context_filter(
        req: GuidelineContextFilterRequest,
        service: GuidelineContextFilterService = Depends(get_guideline_context_filter_service),
) -> GuidelineContextFilterResponse:
    try:
        logger.info(
            "Tools/GuidelineContextFilter: method=%s references=%d filter_input_chars=%d",
            req.settings.method.value,
            len(req.references),
            len(req.filter_input),
        )
        return service.filter_references(req)
    except Exception as e:
        logger.error("Guideline context filter failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
