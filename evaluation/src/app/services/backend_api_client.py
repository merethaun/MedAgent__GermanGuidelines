import json
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests


class BackendApiClient:
    def __init__(
            self,
            session: Optional[requests.Session] = None,
    ):
        self.session = session or requests.Session()
    
    @property
    def base_url(self) -> str:
        return os.getenv("BACKEND_API_BASE_URL", "http://backend:5000").rstrip("/")
    
    @staticmethod
    def _headers(access_token: Optional[str]) -> Dict[str, str]:
        if not access_token:
            raise RuntimeError("A user access token is required for backend access from the evaluation service")
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
    
    def _request(self, method: str, path: str, *, access_token: Optional[str], **kwargs) -> Any:
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            headers=kwargs.pop("headers", self._headers(access_token)),
            timeout=kwargs.pop("timeout", 60*5),
            **kwargs,
        )
        response.raise_for_status()
        if not response.text:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text
    
    def list_guidelines(self, access_token: str) -> List[Dict[str, Any]]:
        return self._request("GET", "/guidelines/", access_token=access_token) or []
    
    def get_workflow(self, workflow_id: str, access_token: str) -> Dict[str, Any]:
        return self._request("GET", f"/system/workflows/{workflow_id}", access_token=access_token)
    
    def get_chat(self, chat_id: str, access_token: str) -> Dict[str, Any]:
        return self._request("GET", f"/system/chats/{chat_id}", access_token=access_token)
    
    def find_bounding_boxes(
            self,
            *,
            access_token: str,
            guideline_id: str,
            text: str,
            start_page: Optional[int] = None,
            end_page: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "guideline_id": guideline_id,
            "text": text,
        }
        if start_page is not None:
            payload["start_page"] = start_page
        if end_page is not None:
            payload["end_page"] = end_page
        return self._request("POST", "/guideline_references/finder", access_token=access_token, data=json.dumps(payload)) or []
    
    def create_chat(self, workflow_id: str, username: str, access_token: str, name: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "workflow_system_id": workflow_id,
            "username": username,
            "name": name,
            "interactions": [],
        }
        return self._request("POST", f"/system/workflows/{workflow_id}/chats", access_token=access_token, data=json.dumps(payload))
    
    @staticmethod
    def _merge_llm_settings(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(base)
        if not override:
            return merged
        
        for key, value in override.items():
            if value in (None, ""):
                continue
            if key in {"extra_headers", "extra_body"}:
                existing = merged.get(key) or {}
                if not isinstance(existing, dict) or not isinstance(value, dict):
                    merged[key] = value
                else:
                    merged[key] = {**existing, **value}
                continue
            merged[key] = value
        return merged
    
    def pose_question(
            self,
            chat_id: str,
            user_input: str,
            access_token: str,
            runtime_llm_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not runtime_llm_settings:
            return self._request(
                "POST",
                f"/system/chats/{chat_id}/pose",
                access_token=access_token,
                params={"user_input": user_input},
            )
        
        payload = {
            "user_input": user_input,
            "runtime_llm_settings": runtime_llm_settings,
        }
        return self._request("POST", f"/system/chats/{chat_id}/pose", access_token=access_token, data=json.dumps(payload))
    
    def embed_texts(self, texts: List[str], access_token: str) -> Dict[str, Any]:
        provider = os.getenv("EVALUATION_EMBEDDING_PROVIDER", "baai-bge-m3")
        payload: Dict[str, Any] = {
            "provider": provider,
            "texts": texts,
            "purpose": "document",
            "normalize": False,
        }
        if provider == "openai-text-embedding-3-large":
            api_key = os.getenv("EVALUATION_EMBEDDING_API_KEY", "")
            if not api_key:
                raise RuntimeError("EVALUATION_EMBEDDING_API_KEY is required for openai-text-embedding-3-large")
            payload["provider_settings"] = {
                "provider": provider,
                "api_key": api_key,
                "base_url": os.getenv("EVALUATION_EMBEDDING_BASE_URL") or None,
                "model": os.getenv("EVALUATION_EMBEDDING_MODEL", "text-embedding-3-large"),
            }
        return self._request("POST", "/vector/embeddings/embed", access_token=access_token, data=json.dumps(payload))
    
    def run_gpt_score(
            self,
            system_prompt: str,
            user_prompt: str,
            access_token: str,
            runtime_llm_settings: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        base_settings = {
            "model": os.getenv("EVALUATION_LLM_MODEL", "gpt-4.1-mini"),
            "api_key": os.getenv("EVALUATION_LLM_API_KEY") or None,
            "base_url": os.getenv("EVALUATION_LLM_BASE_URL") or None,
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 300,
            "timeout_s": int(os.getenv("EVALUATION_LLM_TIMEOUT_S", "60")),
        }
        payload = {
            "session_id": f"evaluation-gptscore-{uuid4()}",
            "system_prompt": system_prompt,
            "llm_settings": self._merge_llm_settings(base_settings, runtime_llm_settings),
        }
        created = self._request("POST", "/tools/llm/sessions", access_token=access_token, data=json.dumps(payload))
        session_id = created["session_id"]
        try:
            response = self._request(
                "POST",
                f"/tools/llm/sessions/{session_id}/chat",
                access_token=access_token,
                data=json.dumps({"prompt": user_prompt}),
            )
            return response.get("response")
        finally:
            try:
                self._request("DELETE", f"/tools/llm/sessions/{session_id}", access_token=access_token)
            except Exception:
                pass
