from typing import Optional

from app.utils.mongo_collection_setup import init_mongo, get_collection
from .auth import AuthService, TokenService
from .knowledge.guideline import GuidelineService
from ..constants.mongodb_config import GUIDELINE_COLLECTION

_auth_service: Optional[AuthService] = None
_token_service: Optional[TokenService] = TokenService()

_guideline_service: Optional[GuidelineService] = None


def init_services() -> None:
    """
    Initialize all singleton services. Call once during app startup.
    """
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    
    init_mongo()
    
    global _guideline_service
    if _guideline_service is None:
        _guideline_service = GuidelineService(guideline_collection=get_collection(GUIDELINE_COLLECTION))


def get_auth_service() -> AuthService:
    """
    Getter used by controllers via Depends(...).
    """
    global _auth_service
    if _auth_service is None:
        init_services()
    return _auth_service


def get_token_service() -> TokenService:
    global _token_service
    if _token_service is None:
        init_services()
    return _token_service


def get_guideline_service() -> GuidelineService:
    global _guideline_service
    if _guideline_service is None:
        init_services()
    assert _guideline_service is not None
    return _guideline_service
