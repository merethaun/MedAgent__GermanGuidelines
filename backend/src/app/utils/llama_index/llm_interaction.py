import json
import os
from typing import Any, List, Union

import requests
from llama_index.core.base.llms.types import CompletionResponse, ChatResponse, ChatMessage, MessageRole, LLMMetadata
from llama_index.core.llms import LLM
from openai import AzureOpenAI, OpenAI
from pydantic import PrivateAttr

from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)


class OllamaLlamaIndexLLM(LLM):
    _api_base: str = PrivateAttr()
    _model: str = PrivateAttr()
    _temperature: float = PrivateAttr()
    _max_tokens: int = PrivateAttr()
    
    def __init__(self, model: str, api_base: str, temperature: float = 0.7, max_tokens: int = 256):
        super().__init__()
        self._api_base = api_base
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
    
    def _post_streaming(self, payload: dict) -> str:
        """Send a streaming request to Ollama and return the concatenated content."""
        url = f"{self._api_base}/api/chat"
        logger.debug(f"[OllamaLlamaIndexLLM] POST {url} (streaming) with payload keys: {list(payload.keys())}")
        try:
            with requests.post(
                    url,
                    json=payload,
                    stream=True,
                    timeout=(60, None),  # connect timeout 10s, no read timeout
                    headers={"Accept": "application/x-ndjson"},
            ) as response:
                logger.debug(f"[OllamaLlamaIndexLLM] HTTP {response.status_code}")
                response.raise_for_status()
                
                chunks: List[str] = []
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        part = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug(f"[OllamaLlamaIndexLLM] Ignoring non-JSON line: {line!r}")
                        continue
                    
                    if part.get("error"):
                        raise RuntimeError(f"Ollama upstream error: {part['error']}")
                    
                    msg = part.get("message") or {}
                    content = msg.get("content")
                    if content:
                        chunks.append(content)
                    
                    if part.get("done"):
                        break
                
                text = "".join(chunks).strip()
                logger.debug(f"[OllamaLlamaIndexLLM] response: {text[:250]}...")
                if not text:
                    raise RuntimeError("Empty streamed response from Ollama.")
                return text
        
        except Exception as e:
            raise RuntimeError(f"[OllamaLlamaIndexLLM] Streaming API error: {e}")
    
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "options": {"num_predict": self._max_tokens},
            "stream": True,  # enable streaming to keep connection alive
        }
        
        text = self._post_streaming(payload)
        return CompletionResponse(text=text)
    
    def chat(self, messages: List[ChatMessage], **kwargs: Any) -> ChatResponse:
        prompt_messages = [{"role": m.role.value, "content": m.content} for m in messages]
        payload = {
            "model": self._model,
            "messages": prompt_messages,
            "temperature": self._temperature,
            "options": {"num_predict": self._max_tokens},
            "stream": True,  # enable streaming
        }
        
        content = self._post_streaming(payload)
        return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content=content))
    
    # Required stubs
    def stream_chat(self, *args, **kwargs):
        raise NotImplementedError()
    
    def stream_complete(self, *args, **kwargs):
        raise NotImplementedError()
    
    def acomplete(self, *args, **kwargs):
        raise NotImplementedError()
    
    def achat(self, *args, **kwargs):
        raise NotImplementedError()
    
    def astream_chat(self, *args, **kwargs):
        raise NotImplementedError()
    
    def astream_complete(self, *args, **kwargs):
        raise NotImplementedError()
    
    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=8192,
            num_output=self._max_tokens,
            is_chat_model=True,
            is_function_calling_model=False,
            model_name=self._model,
        )


class AzureOpenAILlamaIndexLLM(LLM):
    _client: Union[AzureOpenAI, OpenAI] = PrivateAttr()
    _deployment_name: str = PrivateAttr()
    _temperature: float = PrivateAttr()
    _max_tokens: int = PrivateAttr()
    
    def __init__(
            self, api_key: str, api_base: str, deployment_name: str, api_version: str = "2024-07-18", temperature: float = 0.7, max_tokens: int = 512,
    ):
        super().__init__()
        api_type = os.getenv("OPEN_AI_TYPE", "")
        if api_type == "azure":
            self._client = OpenAI(api_key=api_key, base_url=api_base)
            self._deployment_name = deployment_name
        else:
            self._client = OpenAI(api_key=api_key)
            self._deployment_name = deployment_name.replace("azure-", "")
        self._temperature = temperature
        self._max_tokens = max_tokens
    
    _role_map = {
        "system": "system",
        "user": "user",
        "assistant": "assistant",
        "tool": "system",  # e.g., treated as a system message
        "function": "system",  # same
        "chatbot": "assistant",  # remapped to assistant
        "model": "assistant",  # remapped to assistant
    }
    
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        try:
            logger.debug(f"[AzureOpenAILlamaIndexLLM] prompt: {prompt[:100]}...")
            if self._deployment_name.replace("azure-", "") in ["o3", "gpt-5"]:
                response = self._client.chat.completions.create(
                    model=self._deployment_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=self._max_tokens,
                )
            else:
                response = self._client.chat.completions.create(
                    model=self._deployment_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
            text = response.choices[0].message.content or ""
            logger.debug(f"[AzureOpenAILlamaIndexLLM] response: {text[:250]}...")
            return CompletionResponse(text=text)
        except Exception as e:
            raise RuntimeError(f"[AzureOpenAILlamaIndexLLM] API error in complete(): {e}")
    
    def chat(self, messages: List[ChatMessage], **kwargs: Any) -> ChatResponse:
        try:
            logger.debug(f"[AzureOpenAILlamaIndexLLM] messages: {messages}"[:500])
            openai_messages = [{"role": self._role_map[m.role.value], "content": m.content} for m in messages]
            if self._deployment_name.replace("azure-", "") in ["o3", "gpt-5"]:
                response = self._client.chat.completions.create(
                    model=self._deployment_name,
                    messages=openai_messages,
                    max_completion_tokens=self._max_tokens,
                )
            else:
                response = self._client.chat.completions.create(
                    model=self._deployment_name,
                    messages=openai_messages,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
            content = response.choices[0].message.content or ""
            logger.debug(f"[AzureOpenAILlamaIndexLLM] response: {content[:250]}...")
            return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content=content))
        except Exception as e:
            raise RuntimeError(f"[AzureOpenAILlamaIndexLLM] API error in chat(): {e}")
    
    # Required stubs
    def stream_chat(self, *args, **kwargs):
        raise NotImplementedError()
    
    def stream_complete(self, *args, **kwargs):
        raise NotImplementedError()
    
    def acomplete(self, *args, **kwargs):
        raise NotImplementedError()
    
    async def achat(self, messages: List[ChatMessage], **kwargs: Any) -> ChatResponse:
        try:
            logger.debug(f"[AzureOpenAILlamaIndexLLM] async messages: {messages}"[:500])
            
            openai_messages = [{"role": self._role_map[m.role.value], "content": m.content} for m in messages]
            if self._deployment_name.replace("azure-", "") in ["o3", "gpt-5"]:
                response = self._client.chat.completions.create(
                    model=self._deployment_name,
                    messages=openai_messages,
                    max_completion_tokens=self._max_tokens,
                )
            else:
                response = self._client.chat.completions.create(
                    model=self._deployment_name,
                    messages=openai_messages,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
            
            content = response.choices[0].message.content
            logger.debug(f"[AzureOpenAILlamaIndexLLM] async response: {content[:250]}...")
            
            return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content=content))
        
        except Exception as e:
            logger.error(f"[AzureOpenAILlamaIndexLLM] API error in achat(): {e}", exc_info=True)
            raise RuntimeError(f"[AzureOpenAILlamaIndexLLM] API error in achat(): {e}")
    
    def astream_chat(self, *args, **kwargs):
        raise NotImplementedError()
    
    def astream_complete(self, *args, **kwargs):
        raise NotImplementedError()
    
    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=8192,
            num_output=self._max_tokens,
            is_chat_model=True,
            is_function_calling_model=False,
            model_name=self._deployment_name,
        )
