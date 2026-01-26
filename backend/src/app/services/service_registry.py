from typing import Optional

from app.constants.mongodb_config import (
    CHAT_COLLECTION, GUIDELINE_COLLECTION, GUIDELINE_REFERENCE_COLLECTION, GUIDELINE_REFERENCE_GROUP_COLLECTION,
    WORKFLOW_SYSTEM_COLLECTION,
)
from app.utils.mongo_collection_setup import get_collection, init_mongo
from .auth import AuthService, TokenService
from .knowledge.guideline import GuidelineReferenceService, GuidelineService
from .system import WorkflowSystemInteractionService, WorkflowSystemStorageService
from .system.chat import ChatService
from .tools import KeywordService, LLMInteractionService

_auth_service: Optional[AuthService] = None
_token_service: Optional[TokenService] = TokenService()

_guideline_service: Optional[GuidelineService] = None
_guideline_reference_service: Optional[GuidelineReferenceService] = None

_keyword_service: Optional[KeywordService] = None
_llm_interaction_service: Optional[LLMInteractionService] = None

_workflow_storage_service: Optional[WorkflowSystemStorageService] = None
_workflow_interaction_service: Optional[WorkflowSystemInteractionService] = None
_chat_service: Optional[ChatService] = None


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
    
    global _workflow_storage_service
    if _workflow_storage_service is None:
        _workflow_storage_service = WorkflowSystemStorageService(get_collection(WORKFLOW_SYSTEM_COLLECTION))
    
    global _workflow_interaction_service
    if _workflow_interaction_service is None:
        _workflow_interaction_service = WorkflowSystemInteractionService(_workflow_storage_service)
    
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService(chat_collection=get_collection(CHAT_COLLECTION), workflow_interaction_service=_workflow_interaction_service)


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


def get_workflow_storage_service() -> WorkflowSystemStorageService:
    global _workflow_storage_service
    if _workflow_storage_service is None:
        init_services()
    assert _workflow_storage_service is not None
    return _workflow_storage_service


def get_workflow_interaction_service() -> WorkflowSystemInteractionService:
    global _workflow_interaction_service
    if _workflow_interaction_service is None:
        init_services()
    assert _workflow_interaction_service is not None
    return _workflow_interaction_service


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        init_services()
    assert _chat_service is not None
    return _chat_service
