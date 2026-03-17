from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from starlette.responses import StreamingResponse

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import require_roles
from app.exceptions.tools import LLMChatSessionNotFoundError
from app.models.tools.llm_interaction import (
    ChatHistoryResponse,
    ChatTextRequest,
    ChatTextResponse,
    CreateLLMSessionRequest,
    CreateLLMSessionResponse,
    LLMSettings,
    SessionSettingsResponse,
)
from app.services.service_registry import get_llm_interaction_service
from app.services.tools import LLMInteractionService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

llm_router = APIRouter()


@llm_router.post(
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


@llm_router.post(
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


@llm_router.post(
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


@llm_router.get(
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


@llm_router.get(
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


@llm_router.put(
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


@llm_router.post(
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


@llm_router.delete(
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
