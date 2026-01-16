from __future__ import annotations

import asyncio
import os
from typing import Any, List, Optional, Union

from openai import AzureOpenAI, OpenAI
from pydantic import PrivateAttr
from ragas.embeddings.base import BaseRagasEmbeddings

from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)


class AzureOpenAI_RagasEmbeddings(BaseRagasEmbeddings):
    """
    RAGAS embeddings adapter using the official AzureOpenAI SDK client.
    No dataclass; uses PrivateAttr.
    """
    
    _client: Union[AzureOpenAI, OpenAI] = PrivateAttr()
    _deployment: str = PrivateAttr()
    
    def __init__(self, *, api_key: str, azure_endpoint: str, api_version: str, deployment: str, **kwargs: Any):
        super().__init__(**kwargs)
        api_type = os.getenv("OPEN_AI_TYPE", "")
        if api_type == "azure":
            self._client = OpenAI(api_key=api_key, base_url=azure_endpoint)
            self._deployment = deployment
        else:
            self._client = OpenAI(api_key=api_key)
            self._deployment = deployment.replace("azure-", "")
        self._deployment = deployment
    
    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]
    
    async def aembed_query(self, text: str) -> List[float]:
        vecs = await self.aembed_documents([text])
        return vecs[0] if vecs else []
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._deployment, input=texts)
        data_sorted = sorted(resp.data, key=lambda d: d.index)
        return [item.embedding for item in data_sorted]
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)


class HuggingFaceEmbeddingsLocal(BaseRagasEmbeddings):
    _model_name: str = PrivateAttr()
    _device: Optional[str] = PrivateAttr()
    _normalize: bool = PrivateAttr()
    _batch_size: int = PrivateAttr()
    
    # lazy-loaded internals
    _st_model: Any = PrivateAttr(default=None)
    _hf_tokenizer: Any = PrivateAttr(default=None)
    _hf_model: Any = PrivateAttr(default=None)
    _torch: Any = PrivateAttr(default=None)
    _np: Any = PrivateAttr(default=None)
    
    def __init__(
            self, *, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", device: Optional[str] = None, normalize: bool = True,
            batch_size: int = 32, **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._model_name = model_name
        self._device = device
        self._normalize = bool(normalize)
        self._batch_size = int(batch_size)
    
    # --------- read-only properties (optional) ---------
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @property
    def device(self) -> Optional[str]:
        return self._device
    
    @property
    def normalize(self) -> bool:
        return self._normalize
    
    @property
    def batch_size(self) -> int:
        return self._batch_size
    
    # --------- internals ---------
    def _lazy_imports(self):
        if self._np is None:
            import numpy as np
            self._np = np
        if self._torch is None:
            import torch
            self._torch = torch
        if self._st_model is None and self._hf_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._st_model = SentenceTransformer(self._model_name, device=self._device or "cpu")
            except Exception:
                from transformers import AutoTokenizer, AutoModel
                self._hf_tokenizer = AutoTokenizer.from_pretrained(self._model_name)
                self._hf_model = AutoModel.from_pretrained(self._model_name).to(self._device or "cpu")
    
    def _encode_batch(self, texts: List[str]) -> List[List[float]]:
        self._lazy_imports()
        if self._st_model is not None:
            vecs = self._st_model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=self._normalize,
            )
            return [v.tolist() for v in self._np.atleast_2d(vecs)]
        
        # transformers fallback: mean-pool last hidden states
        torch = self._torch
        tok = self._hf_tokenizer
        model = self._hf_model
        out: List[List[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i: i + self._batch_size]
            enc = tok(batch, padding=True, truncation=True, return_tensors="pt").to(model.device)
            with torch.no_grad():
                last_hidden = model(**enc).last_hidden_state  # [B, T, H]
                mask = enc["attention_mask"].unsqueeze(-1)  # [B, T, 1]
                summed = (last_hidden * mask).sum(dim=1)  # [B, H]
                counts = mask.sum(dim=1).clamp(min=1)  # [B, 1]
                pooled = summed / counts
                if self._normalize:
                    pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                out.extend(pooled.cpu().tolist())
        return out
    
    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]
    
    async def aembed_query(self, text: str) -> List[float]:
        vecs = await self.aembed_documents([text])
        return vecs[0] if vecs else []
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self._encode_batch(texts)
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode_batch, texts)
