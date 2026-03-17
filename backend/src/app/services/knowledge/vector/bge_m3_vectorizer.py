import os
from typing import Any, Dict, List, Optional, Tuple

from app.models.knowledge.vector import BGEM3EmbeddingProviderSettings, EmbeddingPurpose
from app.services.knowledge.vector.abstract_vectorizer import AbstractVectorizer
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class BGEM3Vectorizer(AbstractVectorizer):
    provider = "baai-bge-m3"
    display_name = "BAAI bge-m3"
    description = "Local multilingual dense embedding model suited for retrieval across German and English text."
    default_dimension = 1024
    
    def __init__(self):
        self.model_name = os.getenv("BGE_M3_MODEL_NAME", "BAAI/bge-m3")
        self.batch_size = int(os.getenv("BGE_M3_BATCH_SIZE", "8"))
        self._models: Dict[str, Any] = {}
    
    def is_available(self, provider_settings: Optional[BGEM3EmbeddingProviderSettings] = None) -> Tuple[bool, Optional[str]]:
        try:
            import FlagEmbedding  # noqa: F401
        except ImportError:
            return False, "Install 'FlagEmbedding' to enable the local bge-m3 vectorizer."
        except Exception as exc:
            return False, f"FlagEmbedding import failed: {exc}"
        return True, None
    
    def prepare_text(self, text: str, purpose: EmbeddingPurpose) -> str:
        normalized = text.strip()
        if purpose == EmbeddingPurpose.QUERY:
            return f"Represent this query for retrieval: {normalized}"
        return normalized
    
    def _get_model(self, model_name: str):
        if model_name not in self._models:
            from FlagEmbedding import BGEM3FlagModel
            
            logger.info("Loading local embedding model %s", model_name)
            self._models[model_name] = BGEM3FlagModel(model_name, use_fp16=False)
        return self._models[model_name]
    
    def _embed(
            self,
            texts: List[str],
            provider_settings: Optional[BGEM3EmbeddingProviderSettings] = None,
    ) -> List[List[float]]:
        model_name = provider_settings.model_name if provider_settings is not None else self.model_name
        batch_size = provider_settings.batch_size if provider_settings is not None else self.batch_size
        model = self._get_model(model_name)
        logger.info("Embedding %d texts with provider=%s model=%s", len(texts), self.provider, model_name)
        outputs = model.encode(
            texts,
            batch_size=batch_size,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense_vectors = outputs["dense_vecs"]
        if hasattr(dense_vectors, "tolist"):
            return dense_vectors.tolist()
        return [list(vector) for vector in dense_vectors]
