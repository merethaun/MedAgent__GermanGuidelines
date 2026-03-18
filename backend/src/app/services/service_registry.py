from typing import Optional

from app.constants.mongodb_config import (
    CHAT_COLLECTION,
    GUIDELINE_COLLECTION,
    GUIDELINE_REFERENCE_COLLECTION,
    GUIDELINE_REFERENCE_GROUP_COLLECTION,
    VECTOR_COLLECTION_COLLECTION,
    WORKFLOW_SYSTEM_COLLECTION,
)
from app.utils.mongo_collection_setup import get_collection, init_mongo
from .auth import AuthService, TokenService
from .knowledge.guideline import (
    BoundingBoxFinderService,
    GuidelineReferenceChunkingService,
    GuidelineReferenceKeywordService,
    GuidelineReferenceService,
    GuidelineService,
    ReferenceHierarchyIndexService,
)
from .knowledge.vector import EmbeddingService, WeaviateVectorStoreService
from .system import WorkflowSystemInteractionService, WorkflowSystemStorageService
from .system.chat import ChatService
from .tools import GuidelineContextFilterService, GuidelineExpanderService, KeywordService, LLMInteractionService, QueryTransformationService, SnomedService

_auth_service: Optional[AuthService] = None
_token_service: Optional[TokenService] = TokenService()

_bounding_box_finder_service: Optional[BoundingBoxFinderService] = None
_guideline_service: Optional[GuidelineService] = None
_guideline_reference_service: Optional[GuidelineReferenceService] = None
_guideline_reference_chunking_service: Optional[GuidelineReferenceChunkingService] = None
_guideline_reference_keyword_service: Optional[GuidelineReferenceKeywordService] = None
_reference_hierarchy_index_service: Optional[ReferenceHierarchyIndexService] = None
_embedding_service: Optional[EmbeddingService] = None
_weaviate_vector_store_service: Optional[WeaviateVectorStoreService] = None

_keyword_service: Optional[KeywordService] = None
_snomed_service: Optional[SnomedService] = None
_llm_interaction_service: Optional[LLMInteractionService] = None
_guideline_context_filter_service: Optional[GuidelineContextFilterService] = None
_guideline_expander_service: Optional[GuidelineExpanderService] = None

_workflow_storage_service: Optional[WorkflowSystemStorageService] = None
_workflow_interaction_service: Optional[WorkflowSystemInteractionService] = None
_query_transformation_service: Optional[QueryTransformationService] = None
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
    
    global _bounding_box_finder_service
    if _bounding_box_finder_service is None:
        _bounding_box_finder_service = BoundingBoxFinderService()
    
    init_mongo()
    
    global _guideline_service
    if _guideline_service is None:
        _guideline_service = GuidelineService(guideline_collection=get_collection(GUIDELINE_COLLECTION))
    
    global _guideline_reference_service
    if _guideline_reference_service is None:
        _guideline_reference_service = GuidelineReferenceService(
            guideline_collection=get_collection(GUIDELINE_COLLECTION),
            reference_groups_collection=get_collection(GUIDELINE_REFERENCE_GROUP_COLLECTION),
            reference_collection=get_collection(GUIDELINE_REFERENCE_COLLECTION),
        )
    
    global _guideline_reference_chunking_service
    if _guideline_reference_chunking_service is None:
        _guideline_reference_chunking_service = GuidelineReferenceChunkingService(
            reference_service=_guideline_reference_service,
            guideline_service=_guideline_service,
            bounding_box_finder_service=_bounding_box_finder_service,
        )

    global _reference_hierarchy_index_service
    if _reference_hierarchy_index_service is None:
        _reference_hierarchy_index_service = ReferenceHierarchyIndexService(_guideline_reference_service)
    
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    
    global _weaviate_vector_store_service
    if _weaviate_vector_store_service is None:
        _weaviate_vector_store_service = WeaviateVectorStoreService(
            metadata_collection=get_collection(VECTOR_COLLECTION_COLLECTION),
            embedding_service=_embedding_service,
            guideline_service=_guideline_service,
            guideline_reference_service=_guideline_reference_service,
        )

    global _llm_interaction_service
    if _llm_interaction_service is None:
        _llm_interaction_service = LLMInteractionService()
    
    global _keyword_service
    if _keyword_service is None:
        _keyword_service = KeywordService(_llm_interaction_service)

    global _guideline_context_filter_service
    if _guideline_context_filter_service is None:
        _guideline_context_filter_service = GuidelineContextFilterService(_llm_interaction_service)

    global _guideline_expander_service
    if _guideline_expander_service is None:
        _guideline_expander_service = GuidelineExpanderService(
            reference_service=_guideline_reference_service,
            hierarchy_index_service=_reference_hierarchy_index_service,
        )

    global _snomed_service
    if _snomed_service is None:
        _snomed_service = SnomedService(_llm_interaction_service)
    
    global _guideline_reference_keyword_service
    if _guideline_reference_keyword_service is None:
        _guideline_reference_keyword_service = GuidelineReferenceKeywordService(
            reference_service=_guideline_reference_service,
            keyword_service=_keyword_service,
            snomed_service=_snomed_service,
        )
    
    global _workflow_storage_service
    if _workflow_storage_service is None:
        _workflow_storage_service = WorkflowSystemStorageService(get_collection(WORKFLOW_SYSTEM_COLLECTION))
    
    global _workflow_interaction_service
    if _workflow_interaction_service is None:
        _workflow_interaction_service = WorkflowSystemInteractionService(_workflow_storage_service, _llm_interaction_service)
    
    global _query_transformation_service
    if _query_transformation_service is None:
        _query_transformation_service = QueryTransformationService(_llm_interaction_service)
    
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


def get_bounding_box_finder_service() -> BoundingBoxFinderService:
    global _bounding_box_finder_service
    if _bounding_box_finder_service is None:
        init_services()
    assert _bounding_box_finder_service is not None
    return _bounding_box_finder_service


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


def get_guideline_reference_chunking_service() -> GuidelineReferenceChunkingService:
    global _guideline_reference_chunking_service
    if _guideline_reference_chunking_service is None:
        init_services()
    assert _guideline_reference_chunking_service is not None
    return _guideline_reference_chunking_service


def get_guideline_reference_keyword_service() -> GuidelineReferenceKeywordService:
    global _guideline_reference_keyword_service
    if _guideline_reference_keyword_service is None:
        init_services()
    assert _guideline_reference_keyword_service is not None
    return _guideline_reference_keyword_service


def get_reference_hierarchy_index_service() -> ReferenceHierarchyIndexService:
    global _reference_hierarchy_index_service
    if _reference_hierarchy_index_service is None:
        init_services()
    assert _reference_hierarchy_index_service is not None
    return _reference_hierarchy_index_service


def get_keyword_service() -> KeywordService:
    global _keyword_service
    if _keyword_service is None:
        init_services()
    assert _keyword_service is not None
    return _keyword_service


def get_snomed_service() -> SnomedService:
    global _snomed_service
    if _snomed_service is None:
        init_services()
    assert _snomed_service is not None
    return _snomed_service


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        init_services()
    assert _embedding_service is not None
    return _embedding_service


def get_weaviate_vector_store_service() -> WeaviateVectorStoreService:
    global _weaviate_vector_store_service
    if _weaviate_vector_store_service is None:
        init_services()
    assert _weaviate_vector_store_service is not None
    return _weaviate_vector_store_service


def get_llm_interaction_service() -> LLMInteractionService:
    global _llm_interaction_service
    if _llm_interaction_service is None:
        init_services()
    assert _llm_interaction_service is not None
    return _llm_interaction_service


def get_guideline_context_filter_service() -> GuidelineContextFilterService:
    global _guideline_context_filter_service
    if _guideline_context_filter_service is None:
        init_services()
    assert _guideline_context_filter_service is not None
    return _guideline_context_filter_service


def get_guideline_expander_service() -> GuidelineExpanderService:
    global _guideline_expander_service
    if _guideline_expander_service is None:
        init_services()
    assert _guideline_expander_service is not None
    return _guideline_expander_service


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


def get_query_transformation_service() -> QueryTransformationService:
    global _query_transformation_service
    if _query_transformation_service is None:
        init_services()
    assert _query_transformation_service is not None
    return _query_transformation_service


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        init_services()
    assert _chat_service is not None
    return _chat_service
