from abc import ABC, abstractmethod
from typing import Any, List, Optional, Tuple

from app.models.knowledge.vector import EmbeddingPurpose, VectorizerDescriptor


class AbstractVectorizer(ABC):
    """
    Common contract for all embedding providers.

    Vectorizers stay focused on provider-specific concerns while the higher-level
    EmbeddingService handles provider discovery, normalization, and API-facing logic.
    """
    
    provider: str = ""
    display_name: str = ""
    description: str = ""
    default_dimension: Optional[int] = None
    supports_document_embeddings: bool = True
    supports_query_embeddings: bool = True
    
    def get_descriptor(self) -> VectorizerDescriptor:
        is_available, message = self.is_available()
        return VectorizerDescriptor(
            provider=self.provider,
            display_name=self.display_name,
            description=self.description,
            supports_document_embeddings=self.supports_document_embeddings,
            supports_query_embeddings=self.supports_query_embeddings,
            is_available=is_available,
            availability_message=message,
            default_dimension=self.default_dimension,
        )
    
    def is_available(self, provider_settings: Optional[Any] = None) -> Tuple[bool, Optional[str]]:
        return True, None
    
    def embed_texts(
            self,
            texts: List[str],
            purpose: EmbeddingPurpose,
            provider_settings: Optional[Any] = None,
    ) -> List[List[float]]:
        if not texts:
            raise ValueError("texts must not be empty")
        if purpose == EmbeddingPurpose.DOCUMENT and not self.supports_document_embeddings:
            raise ValueError(f"Provider '{self.provider}' does not support document embeddings")
        if purpose == EmbeddingPurpose.QUERY and not self.supports_query_embeddings:
            raise ValueError(f"Provider '{self.provider}' does not support query embeddings")
        prepared_texts = [self.prepare_text(text, purpose) for text in texts]
        return self._embed(prepared_texts, provider_settings)
    
    def prepare_text(self, text: str, purpose: EmbeddingPurpose) -> str:
        return text.strip()
    
    @abstractmethod
    def _embed(self, texts: List[str], provider_settings: Optional[Any] = None) -> List[List[float]]:
        """Return one embedding vector per input text."""
