from typing import List, Optional, Tuple

from app.models.knowledge.vector import OpenAIEmbeddingProviderSettings
from app.services.knowledge.vector.abstract_vectorizer import AbstractVectorizer
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class OpenAITextEmbedding3LargeVectorizer(AbstractVectorizer):
    provider = "openai-text-embedding-3-large"
    display_name = "OpenAI text-embedding-3-large"
    description = "Hosted embedding model for high-quality dense retrieval vectors."
    default_dimension = 3072
    
    def is_available(self, provider_settings: Optional[OpenAIEmbeddingProviderSettings] = None) -> Tuple[bool, Optional[str]]:
        try:
            import openai  # noqa: F401
        except ImportError:
            return False, "Install the 'openai' package to enable this vectorizer."
        
        if provider_settings is None:
            return True, "Provide provider_settings.api_key when calling this provider."
        if not provider_settings.api_key.get_secret_value().strip():
            return False, "provider_settings.api_key must not be empty."
        return True, None
    
    @staticmethod
    def _get_client(provider_settings: OpenAIEmbeddingProviderSettings):
        from openai import OpenAI
        
        client_kwargs = {"api_key": provider_settings.api_key.get_secret_value()}
        if provider_settings.base_url:
            client_kwargs["base_url"] = provider_settings.base_url
        return OpenAI(**client_kwargs)
    
    def _embed(
            self,
            texts: List[str],
            provider_settings: Optional[OpenAIEmbeddingProviderSettings] = None,
    ) -> List[List[float]]:
        if provider_settings is None:
            raise ValueError("OpenAI embeddings require provider_settings with at least an api_key.")
        
        client = self._get_client(provider_settings)
        logger.info(
            "Embedding %d texts with provider=%s model=%s",
            len(texts),
            self.provider,
            provider_settings.model,
        )
        response = client.embeddings.create(
            model=provider_settings.model,
            input=texts,
            encoding_format="float",
        )
        return [list(item.embedding) for item in response.data]
