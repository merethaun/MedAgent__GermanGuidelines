from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, SecretStr, model_validator


class LLMSettings(BaseModel):
    """
    Unified LLM settings for LiteLLM.

    This model is intentionally backend-agnostic and uses optional fields,
    because LiteLLM supports many providers behind one interface.

    Key concepts:
    - `model`: LiteLLM model identifier. Examples:
        - OpenAI: "gpt-4o-mini", "gpt-4.1-mini"
        - Anthropic (via LiteLLM): "anthropic/claude-3-5-sonnet-latest"
        - OpenAI-compatible server: often "openai/<model_name>" with `base_url`
          (depends on your LiteLLM configuration and provider conventions)
        - Ollama (if using LiteLLM's ollama support): e.g. "ollama/llama3.1"
    - `api_key` and `base_url` are optional because not all providers require them.
    - `extra_*` act as escape hatches for provider-specific knobs without changing
      the common interface.

    Practical recommendation:
    - Keep call sites depending only on this settings model.
    - Keep provider quirks inside `extra_body` / `extra_headers` when needed.
    """
    
    # --- Provider/model selection ---
    model: str = Field(
        ...,
        description=(
            "LiteLLM model string, e.g. 'gpt-4.1-mini' or 'anthropic/claude-3-5-sonnet-latest' "
            "or 'ollama/llama3.1'."
        ),
    )
    
    # --- Authentication / routing (optional) ---
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="API key for the provider (optional; many local servers do not require it).",
    )
    base_url: Optional[str] = Field(
        default=None,
        description=(
            "Override base URL (useful for OpenAI-compatible servers like vLLM/LM Studio/Ollama OpenAI shim). "
            "Example: 'http://localhost:11434/v1'."
        ),
    )
    
    # --- Generation defaults (common) ---
    temperature: float = Field(0.2, ge=0.0, le=2.0, description="Sampling temperature.")
    top_p: float = Field(1.0, ge=0.0, le=1.0, description="Nucleus sampling.")
    max_tokens: int = Field(512, ge=1, description="Maximum number of tokens to generate.")
    timeout_s: int = Field(60, ge=1, description="Request timeout in seconds.")
    seed: Optional[int] = Field(None, description="Optional seed if provider supports it.")
    
    # --- Observability / tracing (optional) ---
    request_tags: Dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary tags you want to attach to requests for logging/analytics.",
    )
    
    # --- Escape hatches ---
    extra_headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Extra HTTP headers to forward to provider (reverse proxies, auth gateways, etc.).",
    )
    extra_body: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific request fields forwarded as-is (use sparingly).",
    )
    
    @model_validator(mode="after")
    def _basic_sanity(self) -> "LLMSettings":
        """
        Light sanity checks only.

        Avoid heavy provider-specific validation here because LiteLLM supports many
        providers and conventions.
        """
        if not self.model.strip():
            raise ValueError("LLMSettings.model must not be empty.")
        return self


Message = Dict[str, Any]
"""
Chat message format expected by LiteLLM (OpenAI-style):
    {"role": "system"|"user"|"assistant", "content": "..."}
Content can be string; some providers also support structured content.
"""


@dataclass
class LLMChatSession:
    """
    In-memory chat session.

    Stores:
    - llm_settings: the provider/model/connection + generation defaults used for this session
    - history: OpenAI-style messages (system/user/assistant)
    """
    llm_settings: LLMSettings
    history: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CreateLLMSessionRequest(BaseModel):
    llm_settings: LLMSettings = Field(..., description="LLM settings used for this session only.")
    session_id: Optional[str] = Field(None, description="Optional custom session id. If omitted, server generates one.")
    system_prompt: Optional[str] = Field(None, description="Optional system prompt added as the first message.")
    initial_history: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Optional initial OpenAI-style message history.",
    )


class CreateLLMSessionResponse(BaseModel):
    session_id: str


class ChatTextRequest(BaseModel):
    prompt: str = Field(..., description="User prompt text.")


class ChatTextResponse(BaseModel):
    response: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    history: List[Dict[str, Any]]


class SessionSettingsResponse(BaseModel):
    session_id: str
    llm_settings: LLMSettings
