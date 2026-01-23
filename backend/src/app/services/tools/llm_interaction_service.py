from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from app.exceptions.tools import LLMChatSessionNotFoundError
from app.models.tools.llm_interaction import LLMChatSession, LLMSettings
from app.utils.llm_client import LLMClient, Message
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class LLMInteractionService:
    """
    Very small session-based LLM interaction service.

    What you get:
    - Create a session with specific LLMSettings and optional system prompt.
    - Continue chatting by session_id; history is preserved automatically.
    - Each session can use different providers/models/base_urls, etc.

    Scope:
    - In-memory only (good for admin/testing tools; not multi-worker safe).
    - If you later want persistence (MongoDB), keep the same API and swap storage.
    """
    
    _sessions: Dict[str, LLMChatSession] = field(default_factory=dict)
    
    # -------------------------
    # Session lifecycle
    # -------------------------
    def create_session(
            self,
            llm_settings: LLMSettings,
            *,
            session_id: Optional[str] = None,
            system_prompt: Optional[str] = None,
            initial_history: Optional[List[Message]] = None,
    ) -> str:
        """
        Create a new chat session.

        Args:
            llm_settings: Settings used for this session (provider/model/base_url/etc).
            session_id: Optional external id; if None a UUID is generated.
            system_prompt: Optional system prompt inserted as the first message.
            initial_history: Optional pre-seeded message history (appended after system prompt).

        Returns:
            session_id (string).
        """
        sid = session_id or str(uuid4())
        if sid in self._sessions:
            raise ValueError(f"Session already exists: {sid}")
        
        history: List[Message] = []
        if system_prompt:
            history.append({"role": "system", "content": system_prompt})
        if initial_history:
            history.extend(initial_history)
        
        self._sessions[sid] = LLMChatSession(llm_settings=llm_settings, history=history)
        
        logger.info(
            "Created LLM chat session: session_id=%s model=%s base_url=%s history_len=%d",
            sid,
            llm_settings.model,
            llm_settings.base_url,
            len(history),
        )
        return sid
    
    def delete_session(self, session_id: str) -> None:
        """Delete a session entirely."""
        if session_id not in self._sessions:
            raise LLMChatSessionNotFoundError(f"Unknown session_id: {session_id}")
        self._sessions.pop(session_id, None)
        logger.info("Deleted LLM chat session: session_id=%s", session_id)
    
    def reset_history(self, session_id: str, *, keep_system_prompt: bool = True) -> None:
        """
        Clear a session's history. Optionally keeps the first system message.
        """
        session = self._get_session(session_id)
        if keep_system_prompt and session.history and session.history[0].get("role") == "system":
            session.history = [session.history[0]]
        else:
            session.history = []
        session.updated_at = datetime.now(timezone.utc)
        logger.info("Reset history: session_id=%s keep_system_prompt=%s", session_id, keep_system_prompt)
    
    def update_session_settings(self, session_id: str, llm_settings: LLMSettings) -> None:
        """
        Swap the LLM settings for an existing session (history remains intact).
        """
        session = self._get_session(session_id)
        session.llm_settings = llm_settings
        session.updated_at = datetime.now(timezone.utc)
        logger.info(
            "Updated session settings: session_id=%s model=%s base_url=%s",
            session_id,
            llm_settings.model,
            llm_settings.base_url,
        )
    
    # -------------------------
    # Chat
    # -------------------------
    def chat_text(self, session_id: str, prompt: str) -> str:
        """
        Append a user message, call the LLM using the session's settings, and append assistant response.

        Returns:
            assistant response text
        """
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        
        session = self._get_session(session_id)
        session.history.append({"role": "user", "content": prompt})
        
        logger.info(
            "Chat: session_id=%s model=%s base_url=%s prompt_chars=%d history_len=%d",
            session_id,
            session.llm_settings.model,
            session.llm_settings.base_url,
            len(prompt),
            len(session.history),
        )
        
        try:
            client = LLMClient(session.llm_settings)
            answer = client.chat(session.history, metadata={"session_id": session_id})
        except Exception:
            # Undo the last user message on failure
            session.history.pop()
            raise
        
        session.history.append({"role": "assistant", "content": answer})
        session.updated_at = datetime.now(timezone.utc)
        return answer
    
    def chat_stream_text(self, session_id: str, prompt: str):
        """
        Streaming variant: yields chunks and stores the final assistant message.
        """
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        
        session = self._get_session(session_id)
        session.history.append({"role": "user", "content": prompt})
        
        logger.info(
            "Chat stream: session_id=%s model=%s base_url=%s prompt_chars=%d history_len=%d",
            session_id,
            session.llm_settings.model,
            session.llm_settings.base_url,
            len(prompt),
            len(session.history),
        )
        
        chunks: List[str] = []
        try:
            client = LLMClient(session.llm_settings)
            for piece in client.chat_stream(session.history, metadata={"session_id": session_id}):
                if piece:
                    chunks.append(piece)
                    yield piece
        except Exception:
            session.history.pop()
            raise
        
        answer = "".join(chunks).strip()
        session.history.append({"role": "assistant", "content": answer})
        session.updated_at = datetime.now(timezone.utc)
    
    # -------------------------
    # Inspection
    # -------------------------
    def get_history(self, session_id: str) -> List[Message]:
        """Return a copy of the current session history."""
        session = self._get_session(session_id)
        return list(session.history)
    
    def get_session_settings(self, session_id: str) -> LLMSettings:
        """Return the session's LLMSettings."""
        session = self._get_session(session_id)
        return session.llm_settings
    
    # -------------------------
    # Internal
    # -------------------------
    def _get_session(self, session_id: str) -> LLMChatSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise LLMChatSessionNotFoundError(f"Unknown session_id: {session_id}")
        return session
