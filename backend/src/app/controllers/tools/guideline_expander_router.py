from fastapi import APIRouter, Depends, HTTPException, status

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import require_roles
from app.models.tools.guideline_expander import GuidelineExpanderRequest, GuidelineExpanderResponse
from app.services.service_registry import get_guideline_expander_service
from app.services.tools import GuidelineExpanderService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

guideline_expander_router = APIRouter()


@guideline_expander_router.post(
    "/guideline-expander",
    response_model=GuidelineExpanderResponse,
    status_code=status.HTTP_200_OK,
    summary="Expand guideline references without a workflow (admin only)",
    description=(
        "Expands guideline references either by neighborhood inside a reference group "
        "or by hierarchy section using a persisted reference-group hierarchy index."
    ),
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def guideline_expander(
        req: GuidelineExpanderRequest,
        service: GuidelineExpanderService = Depends(get_guideline_expander_service),
) -> GuidelineExpanderResponse:
    try:
        return service.expand_references(req)
    except Exception as e:
        logger.error("Guideline expander failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
