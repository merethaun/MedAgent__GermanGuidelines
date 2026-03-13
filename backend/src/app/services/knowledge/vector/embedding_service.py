import math
from typing import Dict, List, Optional

from app.exceptions.knowledge.vector import VectorizerNotAvailableError, VectorizerNotFoundError
from app.models.knowledge.vector import EmbeddingProviderSettings, EmbeddingPurpose, VectorizerDescriptor
from app.services.knowledge.vector.abstract_vectorizer import AbstractVectorizer
from app.services.knowledge.vector.bge_m3_vectorizer import BGEM3Vectorizer
from app.services.knowledge.vector.openai_text_embedding_3_large_vectorizer import OpenAITextEmbedding3LargeVectorizer


class EmbeddingService:
    """
    Registry-backed entry point for text embedding generation.

    The service deliberately hides provider-specific details from controllers so
    embedding endpoints can stay small and reusable.
    """

    def __init__(self):
        self._vectorizers: Dict[str, AbstractVectorizer] = {
            OpenAITextEmbedding3LargeVectorizer.provider: OpenAITextEmbedding3LargeVectorizer(),
            BGEM3Vectorizer.provider: BGEM3Vectorizer(),
        }

    def list_vectorizers(self) -> List[VectorizerDescriptor]:
        return [vectorizer.get_descriptor() for vectorizer in self._vectorizers.values()]

    def embed_texts(
            self,
            provider: str,
            texts: List[str],
            *,
            provider_settings: Optional[EmbeddingProviderSettings] = None,
            purpose: EmbeddingPurpose = EmbeddingPurpose.DOCUMENT,
            normalize: bool = False,
    ) -> List[List[float]]:
        vectorizer = self.ensure_vectorizer_available(provider, provider_settings)
        embeddings = vectorizer.embed_texts(texts, purpose, provider_settings=provider_settings)
        if normalize:
            return [self._normalize_vector(vector) for vector in embeddings]
        return embeddings

    def get_vectorizer(self, provider: str) -> AbstractVectorizer:
        vectorizer = self._vectorizers.get(provider)
        if vectorizer is None:
            raise VectorizerNotFoundError(f"Unknown vectorizer provider: {provider}")

        return vectorizer

    def ensure_vectorizer_available(
            self,
            provider: str,
            provider_settings: Optional[EmbeddingProviderSettings] = None,
    ) -> AbstractVectorizer:
        vectorizer = self.get_vectorizer(provider)
        is_available, message = vectorizer.is_available(provider_settings)
        if not is_available:
            raise VectorizerNotAvailableError(message or f"Vectorizer '{provider}' is not available.")
        return vectorizer

    @staticmethod
    def _normalize_vector(vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0:
            return vector
        return [component / norm for component in vector]
