from fastapi import APIRouter, Depends, HTTPException, status

from app.models.auth.token import TokenRequest, TokenResponse
from app.services.auth import TokenService
from app.services.service_registry import get_token_service
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

auth_router = APIRouter()


@auth_router.post("/token", response_model=TokenResponse)
def create_token(
        req: TokenRequest,
        token_service: TokenService = Depends(get_token_service),
) -> TokenResponse:
    try:
        return token_service.create_token(username=req.username, password=req.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception:
        logger.exception("Unexpected error while creating token")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Token creation failed")
