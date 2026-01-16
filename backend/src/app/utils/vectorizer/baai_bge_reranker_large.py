import os
from typing import List

import torch
from FlagEmbedding import BGEM3FlagModel

from app.utils.logger import setup_logger
from app.utils.vectorizer.abstract_vectorizer import AbstractVectorizer

logger = setup_logger(__name__)


class BAAIBilingualGeneralRerankerLarge(AbstractVectorizer):
    """
    Vectorizer using BAAI/bge-reranker-large from Hugging Face. -> https://huggingface.co/BAAI/bge-reranker-large

    Can also do SPARSE!!
    """
    
    def __init__(self):
        logger.debug("Initializing BAAIBilingualGeneralRerankerLarge")
        try:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model_path = os.getenv("BGE_RERANKER_LARGE_PATH", "BAAI/bge-reranker-large")
            self._model = None
            logger.info("BAAIBilingualGeneralRerankerLarge initialized successfully")
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            raise RuntimeError(f"Initialization failed: {e}")
    
    def _ensure_model(self):
        if self._model is None:
            try:
                self._model = BGEM3FlagModel(self.model_path, use_fp16=False)
                logger.info("BAAIBilingualGeneralRerankerLarge initialized successfully")
            except Exception as e:
                logger.error(f"Initialization failed: {e}", exc_info=True)
                raise RuntimeError(f"Initialization failed: {e}")
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        logger.debug(f"[BAAIBilingualGeneralRerankerLarge] Embedding {len(texts)} texts")
        self._ensure_model()
        try:
            outputs = self._model.encode(
                texts,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            dense_vecs = outputs["dense_vecs"]
            
            if hasattr(dense_vecs, "tolist"):
                dense_vecs = dense_vecs.tolist()
            
            logger.info(f"Successfully embedded {len(texts)} dense vectors")
            return dense_vecs
        except Exception as e:
            logger.error(f"[BAAIBilingualGeneralRerankerLarge] Embedding failed: {e}", exc_info=True)
            raise RuntimeError(f"Embedding failed: {e}")
