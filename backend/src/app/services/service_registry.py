from typing import Optional

from app.constants.mongodb_config import GUIDELINE_COLLECTION, GUIDELINE_REFERENCE_COLLECTION, GUIDELINE_REFERENCE_GROUP_COLLECTION
from app.utils.mongo_collection_setup import get_collection, init_mongo
from .auth import AuthService, TokenService
from .knowledge.guideline import GuidelineReferenceService, GuidelineService
from .tools import KeywordService, LLMInteractionService

_auth_service: Optional[AuthService] = None
_token_service: Optional[TokenService] = TokenService()

_guideline_service: Optional[GuidelineService] = None
_guideline_reference_service: Optional[GuidelineReferenceService] = None

_keyword_service: Optional[KeywordService] = None
_llm_interaction_service: Optional[LLMInteractionService] = None


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
    
    global _guideline_reference_service
    if _guideline_reference_service is None:
        _guideline_reference_service = GuidelineReferenceService(
            reference_groups_collection=get_collection(GUIDELINE_REFERENCE_GROUP_COLLECTION),
            reference_collection=get_collection(GUIDELINE_REFERENCE_COLLECTION),
        )
    
    global _keyword_service
    if _keyword_service is None:
        _keyword_service = KeywordService()
    
    global _llm_interaction_service
    if _llm_interaction_service is None:
        _llm_interaction_service = LLMInteractionService()


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


def get_guideline_reference_service() -> GuidelineReferenceService:
    global _guideline_reference_service
    if _guideline_reference_service is None:
        init_services()
    assert _guideline_reference_service is not None
    return _guideline_reference_service


def get_keyword_service() -> KeywordService:
    global _keyword_service
    if _keyword_service is None:
        init_services()
    assert _keyword_service is not None
    return _keyword_service


def get_llm_interaction_service() -> LLMInteractionService:
    global _llm_interaction_service
    if _llm_interaction_service is None:
        init_services()
    assert _llm_interaction_service is not None
    return _llm_interaction_service
