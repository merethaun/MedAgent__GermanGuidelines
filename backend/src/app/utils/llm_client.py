from typing import Any, Dict, Iterable, List, Optional

import litellm

from app.models.tools.llm_interaction import LLMSettings, Message
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class LLMClient:
    """
    Thin wrapper around LiteLLM.

    Goals:
    - Provide a stable API for your application (chat + streaming).
    - Centralize logging and error handling.
    - Keep LiteLLM/provider quirks out of business logic.

    Typical usage:
        settings = LLMSettings(model="gpt-4.1-mini", api_key=SecretStr("..."))
        client = LLMClient(settings)
        text = client.chat([{"role": "user", "content": "Hello!"}])

    Notes on streaming:
    - LiteLLM streaming yields provider-dependent chunks.
    - This wrapper normalizes the common "delta content" extraction.
    """
    
    def __init__(self, settings: LLMSettings):
        self.settings = settings
    
    def _base_kwargs(self) -> Dict[str, Any]:
        """
        Build the base kwargs passed to litellm.completion().

        This is the single place where we translate LLMSettings into a provider call.
        """
        kwargs: Dict[str, Any] = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "max_tokens": self.settings.max_tokens,
            "timeout": self.settings.timeout_s,
        }
        
        if self.settings.seed is not None:
            kwargs["seed"] = self.settings.seed
        
        if self.settings.api_key is not None:
            kwargs["api_key"] = self.settings.api_key.get_secret_value()
        
        if self.settings.base_url is not None:
            kwargs["base_url"] = self.settings.base_url
        
        if self.settings.extra_headers:
            kwargs["extra_headers"] = self.settings.extra_headers
        
        # Provider escape hatch
        if self.settings.extra_body:
            kwargs.update(self.settings.extra_body)
        
        return kwargs
    
    def chat(
            self,
            messages: List[Message],
            *,
            metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Run a non-streaming chat completion and return the assistant text.

        Args:
            messages: OpenAI-style message list.
            metadata: Optional per-call tags (merged with settings.request_tags) for logs.

        Returns:
            Assistant response content as a string.

        Raises:
            RuntimeError: On provider or network errors.
        """
        tags = {**self.settings.request_tags, **(metadata or {})}
        
        logger.info(
            "LLM chat request: model=%s base_url=%s tags=%s",
            self.settings.model,
            self.settings.base_url,
            tags,
        )
        logger.debug(
            "LLM chat request params: temperature=%s top_p=%s max_tokens=%s timeout_s=%s",
            self.settings.temperature,
            self.settings.top_p,
            self.settings.max_tokens,
            self.settings.timeout_s,
        )
        
        try:
            resp = litellm.completion(messages=messages, **self._base_kwargs())
            
            # LiteLLM typically returns OpenAI-like dict/object.
            # Robustly handle both dict and object-ish access.
            choice0 = resp["choices"][0] if isinstance(resp, dict) else resp.choices[0]
            message = choice0["message"] if isinstance(choice0, dict) else choice0.message
            content = message.get("content") if isinstance(message, dict) else message.content
            
            if not content:
                raise RuntimeError("Empty response content from LLM provider.")
            
            logger.info("LLM chat success: model=%s chars=%d", self.settings.model, len(content))
            return content
        
        except Exception as e:
            logger.error("LLM chat failed: model=%s error=%s", self.settings.model, str(e), exc_info=True)
            raise RuntimeError(f"LLM chat failed: {e}") from e
    
    def chat_stream(
            self,
            messages: List[Message],
            *,
            metadata: Optional[Dict[str, str]] = None,
    ) -> Iterable[str]:
        """
        Run a streaming chat completion.

        Yields:
            Text chunks as they arrive.

        Notes:
            - Chunk format differs between providers; we extract the common delta content.
            - If you need richer streaming events, you can yield the raw chunks instead.
        """
        tags = {**self.settings.request_tags, **(metadata or {})}
        
        logger.info(
            "LLM streaming request: model=%s base_url=%s tags=%s",
            self.settings.model,
            self.settings.base_url,
            tags,
        )
        
        try:
            stream = litellm.completion(messages=messages, stream=True, **self._base_kwargs())
            emitted_any = False
            
            for chunk in stream:
                # Chunk can be dict-like or object-like
                text = self._extract_stream_text(chunk)
                if text:
                    emitted_any = True
                    yield text
            
            if not emitted_any:
                logger.warning("LLM streaming ended without content: model=%s", self.settings.model)
        
        except Exception as e:
            logger.error("LLM streaming failed: model=%s error=%s", self.settings.model, str(e), exc_info=True)
            raise RuntimeError(f"LLM streaming failed: {e}") from e
    
    @staticmethod
    def _extract_stream_text(chunk: Any) -> Optional[str]:
        """
        Attempt to extract incremental text from a LiteLLM streaming chunk.

        Handles common OpenAI-like chunk shapes:
            {"choices":[{"delta":{"content":"..."}}]}
        """
        try:
            if isinstance(chunk, dict):
                choices = chunk.get("choices") or []
                if not choices:
                    return None
                delta = choices[0].get("delta") or {}
                return delta.get("content")
            else:
                # object-like
                choices = getattr(chunk, "choices", None)
                if not choices:
                    return None
                delta = getattr(choices[0], "delta", None)
                if not delta:
                    return None
                return getattr(delta, "content", None)
        except Exception:
            return None
    
    def chat_text(
            self,
            prompt: str,
            *,
            system_prompt: Optional[str] = None,
            history: Optional[List[Message]] = None,
            metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Convenience wrapper for simple use cases where the caller provides a plain input string.

        Args:
            prompt: User prompt text.
            system_prompt: Optional system instruction prepended as the first message.
            history: Optional prior messages (OpenAI-style) to preserve conversation context.
            metadata: Optional per-call tags merged into logs.

        Returns:
            Assistant response text.
        """
        if history is None:
            history = []
        
        messages: List[Message] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Keep caller-provided history (already OpenAI-style)
        messages.extend(history)
        
        # Add new user prompt
        messages.append({"role": "user", "content": prompt})
        
        logger.debug(
            "LLM chat_text: prompt_chars=%d system_prompt=%s history_len=%d",
            len(prompt),
            bool(system_prompt),
            len(history),
        )
        
        return self.chat(messages, metadata=metadata)
