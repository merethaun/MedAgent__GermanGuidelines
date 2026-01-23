from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from starlette.responses import StreamingResponse

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import require_roles
from app.exceptions.tools import LLMChatSessionNotFoundError
from app.models.tools.keyword_interaction import KeywordBothResponse, KeywordExtractionResponse, KeywordLLMRequest, KeywordYakeRequest
from app.models.tools.llm_interaction import (
    ChatHistoryResponse, ChatTextRequest, ChatTextResponse, CreateLLMSessionRequest, CreateLLMSessionResponse, LLMSettings,
    SessionSettingsResponse,
)
from app.services.service_registry import get_keyword_service, get_llm_interaction_service
from app.services.tools import KeywordService, LLMInteractionService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

tool_router = APIRouter()


#################################
# ------- Keyword test ---------#
#################################

@tool_router.get(
    "/keywords/defaults",
    response_model=Dict[str, Any],
    summary="Get keyword extraction defaults (admin only)",
    description="Returns DEFAULT_KEYWORD_SETTINGS and prompt template info for debugging.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def get_keyword_defaults() -> Dict[str, Any]:
    try:
        # Import from the service module to avoid duplicating constants
        from app.services.tools.keyword_service import DEFAULT_KEYWORD_SETTINGS, KEYWORDS_PROMPT  # noqa
        
        return {
            "DEFAULT_KEYWORD_SETTINGS": DEFAULT_KEYWORD_SETTINGS,
            "KEYWORDS_PROMPT_preview": KEYWORDS_PROMPT[:500] + " ...",
        }
    except Exception as e:
        logger.error("Failed to return keyword defaults: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.post(
    "/keywords/yake",
    response_model=KeywordExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract keywords via YAKE (admin only)",
    description="Runs KeywordService.extract_yake() on the provided text.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def extract_keywords_yake(
        req: KeywordYakeRequest,
        service: KeywordService = Depends(get_keyword_service),
) -> KeywordExtractionResponse:
    try:
        logger.info("Tools/Keywords YAKE: text_len=%d lang=%s", len(req.text), req.language)
        
        keywords = service.extract_yake(
            text=req.text,
            language=req.language,
            min_keywords=req.min_keywords,
            max_keywords=req.max_keywords,
            max_n_gram_size=req.max_n_gram_size,
            deduplication_threshold=req.deduplication_threshold,
            ignore_terms=req.ignore_terms,
            suppress_subphrases=req.suppress_subphrases,
            headroom=req.headroom,
        )
        
        return KeywordExtractionResponse(keywords=keywords)
    
    except Exception as e:
        logger.error("YAKE keyword extraction failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.post(
    "/keywords/llm",
    response_model=KeywordExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract keywords via LLM (admin only)",
    description="Runs KeywordService.extract_llm() on the provided text and LLM settings.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def extract_keywords_llm(
        req: KeywordLLMRequest,
        service: KeywordService = Depends(get_keyword_service),
) -> KeywordExtractionResponse:
    try:
        logger.info(
            "Tools/Keywords LLM: text_len=%d model=%s base_url=%s",
            len(req.text),
            getattr(req.llm_settings, "model", None),
            getattr(req.llm_settings, "base_url", None),
        )
        
        keywords = service.extract_llm(
            req.text,
            llm_settings=req.llm_settings,
            scope_description=req.scope_description,
            guidance_additions=req.guidance_additions,
            ignore_terms=req.ignore_terms,
            important_terms=req.important_terms,
            examples=req.examples,
            min_keywords=req.min_keywords,
            max_keywords=req.max_keywords,
        )
        
        return KeywordExtractionResponse(keywords=keywords)
    
    except Exception as e:
        logger.error("LLM keyword extraction failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.post(
    "/keywords/both",
    response_model=KeywordBothResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract keywords via YAKE + LLM (admin only)",
    description="Runs both extractors and returns both lists plus overlap/union.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def extract_keywords_both(
        text: str = Query(..., description="Input text passage"),
        language: str = Query("de", description="YAKE language code"),
        min_keywords: Optional[int] = Query(None, ge=1, description="Minimum desired keywords"),
        max_keywords: Optional[int] = Query(None, ge=1, description="Maximum desired keywords"),
        # LLM settings passed in body (so you can keep secrets out of query params)
        llm_settings: LLMSettings = Depends(),  # NOTE: if you prefer, move to request body with a BaseModel
        service: KeywordService = Depends(get_keyword_service),
) -> KeywordBothResponse:
    """
    Combined endpoint to quickly verify both keyword paths.

    If you prefer a single body model, replace this signature with KeywordLLMRequest + extra YAKE fields.
    """
    try:
        logger.info("Tools/Keywords BOTH: text_len=%d lang=%s", len(text), language)
        
        yake_kw = service.extract_yake(
            text=text,
            language=language,
            min_keywords=min_keywords,
            max_keywords=max_keywords,
        )
        
        llm_kw = service.extract_llm(
            text,
            llm_settings=llm_settings,
            min_keywords=min_keywords,
            max_keywords=max_keywords,
        )
        
        overlap = sorted(set(yake_kw).intersection(set(llm_kw)))
        union = sorted(set(yake_kw).union(set(llm_kw)))
        
        return KeywordBothResponse(yake=yake_kw, llm=llm_kw, overlap=overlap, union=union)
    
    except Exception as e:
        logger.error("BOTH keyword extraction failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


#################################
# ------- LLM tool test --------#
#################################

@tool_router.post(
    "/llm/sessions",
    response_model=CreateLLMSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new LLM chat session (admin only)",
    description="Creates an in-memory session with its own LLMSettings and optional system prompt.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_llm_session(
        req: CreateLLMSessionRequest,
        service: LLMInteractionService = Depends(get_llm_interaction_service),
) -> CreateLLMSessionResponse:
    try:
        logger.info(
            "Tools/LLM create session: model=%s base_url=%s has_system=%s",
            getattr(req.llm_settings, "model", None),
            getattr(req.llm_settings, "base_url", None),
            bool(req.system_prompt),
        )
        session_id = service.create_session(
            llm_settings=req.llm_settings,
            session_id=req.session_id,
            system_prompt=req.system_prompt,
            initial_history=req.initial_history,
        )
        return CreateLLMSessionResponse(session_id=session_id)
    except Exception as e:
        logger.error("Create LLM session failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.post(
    "/llm/sessions/{session_id}/chat",
    response_model=ChatTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with an existing LLM session (admin only)",
    description="Appends the user prompt to session history, calls the LLM, appends the assistant answer.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def llm_chat_text(
        session_id: str,
        req: ChatTextRequest,
        service: LLMInteractionService = Depends(get_llm_interaction_service),
) -> ChatTextResponse:
    try:
        logger.info("Tools/LLM chat: session_id=%s prompt_chars=%d", session_id, len(req.prompt))
        response = service.chat_text(session_id=session_id, prompt=req.prompt)
        return ChatTextResponse(response=response)
    except LLMChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("LLM chat failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.post(
    "/llm/sessions/{session_id}/chat/stream",
    summary="Stream chat response for an existing session (admin only)",
    description="Streams the LLM response. The final response is still stored in session history.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def llm_chat_stream(
        session_id: str,
        req: ChatTextRequest,
        service: LLMInteractionService = Depends(get_llm_interaction_service),
):
    try:
        logger.info("Tools/LLM chat stream: session_id=%s prompt_chars=%d", session_id, len(req.prompt))
        
        def gen():
            for piece in service.chat_stream_text(session_id=session_id, prompt=req.prompt):
                yield piece
        
        return StreamingResponse(gen(), media_type="text/plain")
    
    except LLMChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("LLM stream failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.get(
    "/llm/sessions/{session_id}/history",
    response_model=ChatHistoryResponse,
    summary="Get session history (admin only)",
    description="Returns the OpenAI-style message history stored for the session.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def llm_get_history(
        session_id: str,
        service: LLMInteractionService = Depends(get_llm_interaction_service),
) -> ChatHistoryResponse:
    try:
        history = service.get_history(session_id)
        return ChatHistoryResponse(session_id=session_id, history=history)
    except LLMChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Get history failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.get(
    "/llm/sessions/{session_id}/settings",
    response_model=SessionSettingsResponse,
    summary="Get session LLM settings (admin only)",
    description="Returns the LLMSettings associated with this session.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def llm_get_settings(
        session_id: str,
        service: LLMInteractionService = Depends(get_llm_interaction_service),
) -> SessionSettingsResponse:
    try:
        settings = service.get_session_settings(session_id)
        return SessionSettingsResponse(session_id=session_id, llm_settings=settings)
    except LLMChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Get settings failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.put(
    "/llm/sessions/{session_id}/settings",
    response_model=SessionSettingsResponse,
    summary="Update session LLM settings (admin only)",
    description="Replaces the LLMSettings for an existing session (history is preserved).",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def llm_update_settings(
        session_id: str,
        llm_settings: LLMSettings = Body(...),
        service: LLMInteractionService = Depends(get_llm_interaction_service),
) -> SessionSettingsResponse:
    try:
        logger.info(
            "Tools/LLM update settings: session_id=%s model=%s base_url=%s",
            session_id,
            getattr(llm_settings, "model", None),
            getattr(llm_settings, "base_url", None),
        )
        service.update_session_settings(session_id, llm_settings)
        return SessionSettingsResponse(session_id=session_id, llm_settings=service.get_session_settings(session_id))
    except LLMChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Update settings failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.post(
    "/llm/sessions/{session_id}/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset session history (admin only)",
    description="Clears session history. Keeps the system prompt by default.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def llm_reset_history(
        session_id: str,
        keep_system_prompt: bool = Query(True, description="Keep system prompt (first message) if present."),
        service: LLMInteractionService = Depends(get_llm_interaction_service),
) -> None:
    try:
        service.reset_history(session_id, keep_system_prompt=keep_system_prompt)
        return None
    except LLMChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Reset history failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@tool_router.delete(
    "/llm/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an LLM session (admin only)",
    description="Deletes the entire session (history + settings).",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def llm_delete_session(
        session_id: str,
        service: LLMInteractionService = Depends(get_llm_interaction_service),
) -> None:
    try:
        service.delete_session(session_id)
        return None
    except LLMChatSessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Delete session failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
