import os
from threading import Lock
from typing import List

import torch
from transformers import AutoTokenizer, AutoModel

from app.utils.logger import setup_logger
from app.utils.vectorizer.abstract_vectorizer import AbstractVectorizer

logger = setup_logger(__name__)


class BAAILLMEmbedder(AbstractVectorizer):
    """
    Vectorizer using BAAI/llm-embedder from Hugging Face. -> https://huggingface.co/BAAI/llm-embedder
    """
    
    def __init__(self):
        logger.debug("Initializing BAAILLMEmbedder (lazy)")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_path = os.getenv("LLM_EMBEDDER_PATH", "BAAI/llm-embedder")
        self._tokenizer = None
        self._model = None
        self._lock = Lock()
    
    def _ensure_model(self):
        if self._model is not None and self._tokenizer is not None:
            return
        with self._lock:
            if self._model is not None and self._tokenizer is not None:
                return
            try:
                # If running offline, force local cache only
                local_only = (
                        os.getenv("TRANSFORMERS_OFFLINE", "0") == "1"
                        or os.getenv("HF_HUB_OFFLINE", "0") == "1"
                )
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.model_path, local_files_only=local_only,
                )
                self._model = AutoModel.from_pretrained(
                    self.model_path, local_files_only=local_only,
                ).to(self.device)
                logger.info(f"BAAILLMEmbedder loaded from {self.model_path}")
            except Exception as e:
                logger.error(f"BAAILLMEmbedder init failed: {e}", exc_info=True)
                raise RuntimeError(f"BAAILLMEmbedder init failed: {e}")
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        logger.debug(f"[BAAILLMEmbedder] Embedding {len(texts)} texts")
        self._ensure_model()
        try:
            inputs = self._tokenizer(texts, padding=True, truncation=True, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self._model(**inputs)
                # Mean pool + L2 normalize (often better than CLS for embeddings)
                last_hidden = outputs.last_hidden_state
                mask = inputs.attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
                summed = torch.sum(last_hidden * mask, dim=1)
                counts = torch.clamp(mask.sum(dim=1), min=1e-9)
                embeddings = summed / counts
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                
                # If you want CLS instead, use the next line and remove the mean-pool above:
                # embeddings = outputs.last_hidden_state[:, 0]
            
            return embeddings.cpu().numpy().tolist()
        except Exception as e:
            logger.error(f"[BAAILLMEmbedder] Embedding failed: {e}", exc_info=True)
            raise RuntimeError(f"Embedding failed: {e}")
