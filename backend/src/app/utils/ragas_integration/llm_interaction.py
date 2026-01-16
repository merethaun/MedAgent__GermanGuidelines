import asyncio
import os
import typing as t
from typing import Any, List, Optional, Union
from typing import Dict

import requests
from langchain_core.callbacks import Callbacks
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult
from langchain_core.outputs.chat_generation import ChatGeneration
from langchain_core.prompt_values import PromptValue
from openai import AzureOpenAI, OpenAI
from pydantic import PrivateAttr
from ragas.llms.base import BaseRagasLLM

from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)


class AzureOpenAI_RagasLLM(BaseRagasLLM):
    # --- required private attrs ---
    _client: Union[AzureOpenAI, OpenAI] = PrivateAttr()
    _deployment: str = PrivateAttr()
    _temperature: float = PrivateAttr()
    _max_tokens: int = PrivateAttr()
    
    def __init__(
            self, *, api_key: str, azure_endpoint: str, api_version: str, deployment: str, temperature: float = 0.0, max_tokens: int = 512, **kwargs,
    ):
        super().__init__(**kwargs)
        
        api_type = os.getenv("OPEN_AI_TYPE")
        if api_type == "azure":
            self._client = OpenAI(api_key=api_key, base_url=azure_endpoint)
            self._deployment = deployment
        else:
            self._client = OpenAI(api_key=api_key)
            self._deployment = deployment.replace("azure-", "")
        self._temperature = float(temperature)
        self._max_tokens = int(max_tokens)
    
    @property
    def temperature(self) -> float:
        return self._temperature
    
    @property
    def max_tokens(self) -> int:
        return self._max_tokens
    
    def complete(
            self, prompt: str, *, temperature: Optional[float] = None, stop: Optional[List[str]] = None, max_tokens: Optional[int] = None,
    ) -> str:
        """Simple single-turn completion: returns text only."""
        temp = float(temperature) if temperature is not None else self._temperature
        mtok = int(max_tokens) if max_tokens is not None else self._max_tokens
        
        logger.debug(f"[AzureOpenAI_RagasLLM.complete] temp={temp} max_tokens={mtok}")
        
        if self._deployment in ["o3", "gpt-5"]:
            resp = self._client.chat.completions.create(
                model=self._deployment,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=mtok,
                stop=stop,
            )
        else:
            resp = self._client.chat.completions.create(
                model=self._deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=temp,
                max_tokens=mtok,
                stop=stop,
            )
        return (resp.choices[0].message.content or "").strip()
    
    def chat(
            self, messages: List[dict], *, temperature: Optional[float] = None, stop: Optional[List[str]] = None, max_tokens: Optional[int] = None,
    ) -> str:
        """Multi-turn call with provided messages."""
        temp = float(temperature) if temperature is not None else self._temperature
        mtok = int(max_tokens) if max_tokens is not None else self._max_tokens
        
        logger.debug(f"[AzureOpenAI_RagasLLM.chat] temp={temp} max_tokens={mtok} #msgs={len(messages)}")
        
        if self._deployment in ["o3", "gpt-5"]:
            resp = self._client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                max_completion_tokens=mtok,
                step=stop,
            )
        else:
            resp = self._client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                temperature=temp,
                max_tokens=mtok,
                stop=stop,
            )
        return (resp.choices[0].message.content or "").strip()
    
    def _complete_chat(self, prompt, stop, temperature) -> ChatGeneration:
        temp = float(temperature) if temperature is not None else self._temperature
        resp = self._client.chat.completions.create(
            model=self._deployment,
            messages=[{"role": "user", "content": prompt.to_string()}],
            temperature=temp,
            max_tokens=self._max_tokens,
            stop=stop,
        )
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        finish_reason = (choice.finish_reason or "stop")
        return ChatGeneration(
            text=text,
            message=AIMessage(content=text, response_metadata={"finish_reason": finish_reason}),
            generation_info={"finish_reason": finish_reason},
        )
    
    def is_finished(self, result: LLMResult) -> bool:
        try:
            gens = result.generations[0]
        except Exception:
            return True
        ok = {"stop", "length", "content_filter"}
        for g in gens:
            fr = (g.generation_info or {}).get("finish_reason", "stop")
            if fr not in ok:
                return False
        return True
    
    def generate_text(
            self, prompt: PromptValue, n: int = 1, temperature: float = 1e-8, stop: t.Optional[t.List[str]] = None, callbacks: Callbacks = None,
    ) -> LLMResult:
        gens = [self._complete_chat(prompt, stop, temperature) for _ in range(max(1, int(n)))]
        return LLMResult(generations=[gens])
    
    async def agenerate_text(
            self, prompt, n: int = 1, temperature: Optional[float] = None, stop: Optional[List[str]] = None, callbacks=None,
    ) -> LLMResult:
        calls = [
            asyncio.to_thread(self._complete_chat, prompt, stop, temperature)
            for _ in range(max(1, int(n)))
        ]
        gens = await asyncio.gather(*calls)
        return LLMResult(generations=[gens])


class Ollama_RagasLLM(BaseRagasLLM):
    _api_base: str = PrivateAttr()
    _model: str = PrivateAttr()
    _temperature: float = PrivateAttr()
    _max_tokens: int = PrivateAttr()
    _request_timeout: float = PrivateAttr()
    _think: bool = PrivateAttr()
    _chat_history: List[Dict[str, str]] = PrivateAttr(default_factory=list)
    
    def __init__(
            self, api_base: Optional[str] = None, model: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None,
            request_timeout: Optional[float] = None, think: Optional[bool] = None, **kwargs: Any,
    ):
        # NOTE: BaseRagasLLM (pydantic model) init first
        super().__init__(**kwargs)
        
        # Apply env-driven defaults
        self._api_base = api_base or os.getenv("WARHOL_OLLAMA_API_BASE", "http://localhost:11434")
        self._model = model or os.getenv("OLLAMA_MODEL_NAME", "deepseek-r1:7b")
        self._temperature = float(temperature if temperature is not None else os.getenv("OLLAMA_TEMPERATURE", 0.7))
        self._max_tokens = int(max_tokens if max_tokens is not None else os.getenv("OLLAMA_MAX_TOKENS", 256))
        self._request_timeout = float(request_timeout if request_timeout is not None else os.getenv("OLLAMA_TIMEOUT_SECONDS", 120.0))
        self._think = bool(think if think is not None else False)
    
    @property
    def api_base(self) -> str:
        return self._api_base
    
    @property
    def model(self) -> str:
        return self._model
    
    @property
    def temperature(self) -> float:
        return self._temperature
    
    @property
    def max_tokens(self) -> int:
        return self._max_tokens
    
    def reset_history(self) -> None:
        self._chat_history.clear()
    
    def generate_response(self, prompt: str) -> str:
        """
        Stateful chat call (maintains self._chat_history) like your AbstractGenerator.
        """
        self._chat_history.append({"role": "user", "content": prompt})
        url = f"{self._api_base}/api/chat"
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": self._chat_history,
            "temperature": self._temperature,
            "options": {"num_predict": self._max_tokens},
            "stream": False,
            "think": bool(self._think),
        }
        
        try:
            logger.debug(f"[Ollama_RagasLLM] POST {url}")
            response = requests.post(url, json=payload, timeout=self._request_timeout)
            logger.debug(f"[Ollama_RagasLLM] status={response.status_code} content={response.content[:500]}...")
            response.raise_for_status()
            data = response.json()
            text = (data.get("message") or {}).get("content", "") or ""
        except requests.exceptions.JSONDecodeError as e:
            self._chat_history.pop()  # rollback last user turn
            logger.error(f"[Ollama_RagasLLM] JSON decode error: {e}")
            logger.debug(f"[Ollama_RagasLLM] Raw response: {getattr(response, 'text', '')[:500]}...")
            raise RuntimeError(f"Ollama_RagasLLM invalid JSON: {e}")
        except ValueError as e:
            # .json() may raise ValueError in some setups
            self._chat_history.pop()
            logger.error(f"[Ollama_RagasLLM] JSON parse error: {e}")
            logger.debug(f"[Ollama_RagasLLM] Raw response: {getattr(response, 'text', '')[:500]}...")
            raise RuntimeError(f"Ollama_RagasLLM invalid JSON: {e}")
        except Exception as e:
            self._chat_history.pop()
            logger.error(f"[Ollama_RagasLLM] API error: {e}", exc_info=True)
            raise RuntimeError(f"Ollama_RagasLLM error: {e}")
        
        self._chat_history.append({"role": "assistant", "content": text})
        logger.debug(f"[Ollama_RagasLLM] Response: {text[:500]}...")
        return text
    
    def is_finished(self, result: LLMResult) -> bool:
        try:
            gens = result.generations[0]
        except Exception:
            return True
        ok = {"stop", "length", "content_filter"}
        for g in gens:
            fr = (g.generation_info or {}).get("finish_reason", "stop")
            if fr not in ok:
                return False
        return True
    
    def complete(
            self,
            prompt: str,
            *,
            stop: Optional[List[str]] = None,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
    ) -> str:
        """
        Stateless single-turn completion. Does not touch history.
        """
        return self._chat(
            messages=[{"role": "user", "content": prompt}],
            stop=stop,
            temperature=self._temperature if temperature is None else float(temperature),
            max_tokens=self._max_tokens if max_tokens is None else int(max_tokens),
        )
    
    def chat(
            self,
            messages: List[Dict[str, str]],
            *,
            stop: Optional[List[str]] = None,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
    ) -> str:
        """
        Stateless multi-turn call with provided messages.
        """
        return self._chat(
            messages=messages,
            stop=stop,
            temperature=self._temperature if temperature is None else float(temperature),
            max_tokens=self._max_tokens if max_tokens is None else int(max_tokens),
        )
    
    def _complete_chat(self, prompt, stop, temperature) -> ChatGeneration:
        txt = self.complete(prompt.to_string(), stop=stop, temperature=temperature)
        return ChatGeneration(
            text=txt,
            message=AIMessage(content=txt, response_metadata={"finish_reason": "stop"}),
            generation_info={"finish_reason": "stop"},
        )
    
    def generate_text(
            self, prompt: PromptValue, n: int = 1, temperature: float = 1e-8, stop: t.Optional[t.List[str]] = None, callbacks: Callbacks = None,
    ) -> LLMResult:
        temp = self._temperature if temperature is None else float(temperature)
        gens = [self._complete_chat(prompt, stop, temp) for _ in range(max(1, int(n)))]
        return LLMResult(generations=[gens])
    
    async def agenerate_text(
            self, prompt, n: int = 1, temperature: Optional[float] = None, stop: Optional[List[str]] = None, callbacks=None,
    ) -> LLMResult:
        """
        RAGAS entrypoint: run stateless complete() n times in a threadpool and
        wrap into LLMResult/ChatGeneration for compatibility.
        """
        temp = self._temperature if temperature is None else float(temperature)
        calls = [
            asyncio.to_thread(self._complete_chat, prompt, stop, temp)
            for _ in range(max(1, int(n)))
        ]
        gens = await asyncio.gather(*calls)
        return LLMResult(generations=[gens])
    
    def _chat(
            self, *, messages: List[Dict[str, str]], stop: Optional[List[str]], temperature: float, max_tokens: int,
    ) -> str:
        url = f"{self._api_base}/api/chat"
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": float(temperature),
            "options": {"num_predict": int(max_tokens)},
            "stream": False,
            "think": bool(self._think),
        }
        if stop:
            payload["options"]["stop"] = stop
        
        try:
            logger.debug(f"[Ollama_RagasLLM._chat] POST {url}")
            r = requests.post(url, json=payload, timeout=self._request_timeout)
            logger.debug(f"[Ollama_RagasLLM._chat] status={r.status_code} content={r.content[:500]}...")
            r.raise_for_status()
            data = r.json()
            return (data.get("message") or {}).get("content", "") or ""
        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"[Ollama_RagasLLM._chat] JSON decode error: {e}")
            logger.debug(f"[Ollama_RagasLLM._chat] Raw response: {getattr(r, 'text', '')[:500]}...")
            raise RuntimeError(f"Ollama_RagasLLM invalid JSON: {e}")
        except ValueError as e:
            logger.error(f"[Ollama_RagasLLM._chat] JSON parse error: {e}")
            logger.debug(f"[Ollama_RagasLLM._chat] Raw response: {getattr(r, 'text', '')[:500]}...")
            raise RuntimeError(f"Ollama_RagasLLM invalid JSON: {e}")
        except Exception as e:
            logger.error(f"[Ollama_RagasLLM._chat] API error: {e}", exc_info=True)
            raise RuntimeError(f"Ollama_RagasLLM API error: {e}")
