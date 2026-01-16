import os
from typing import List

import torch
from FlagEmbedding import BGEM3FlagModel

from app.utils.logger import setup_logger
from app.utils.vectorizer.abstract_vectorizer import AbstractVectorizer

logger = setup_logger(__name__)


class BAAIBilingualGeneralEmbedderM3(AbstractVectorizer):
    """
    Vectorizer using BAAI/bge-m3 model from Hugging Face. -> https://huggingface.co/BAAI/bge-m3
    
    Can also do SPARSE!!
    """
    
    def __init__(self):
        logger.debug("Initializing BAAIBilingualGeneralEmbedder3")
        try:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model_path = os.getenv("BGE_M3_PATH", "BAAI/bge-m3")
            self._model = None
            logger.info("BAAIBilingualGeneralEmbedder3 initialized successfully")
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            raise RuntimeError(f"Initialization failed: {e}")
    
    def _ensure_model(self):
        if self._model is None:
            try:
                self._model = BGEM3FlagModel(self.model_path, use_fp16=False)
                logger.info("BAAIBilingualGeneralEmbedder3 initialized successfully")
            except Exception as e:
                logger.error(f"Initialization failed: {e}", exc_info=True)
                raise RuntimeError(f"Initialization failed: {e}")
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        logger.debug(f"[BAAIBilingualGeneralEmbedder3] Embedding {len(texts)} texts")
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
            logger.error(f"[BAAIBilingualGeneralEmbedder3] Embedding failed: {e}", exc_info=True)
            raise RuntimeError(f"Embedding failed: {e}")
