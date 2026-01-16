import os
from typing import List

from openai import AzureOpenAI, OpenAI

from app.utils.logger import setup_logger
from app.utils.vectorizer.abstract_vectorizer import AbstractVectorizer

logger = setup_logger(__name__)


class OpenAI3LargeEmbedder(AbstractVectorizer):
    """
    Vectorizer using Azure OpenAI with text-embedding-3-large.
    """
    
    def __init__(self):
        logger.debug("Initializing OpenAI3LargeEmbedder")
        api_type = os.getenv("OPEN_AI_TYPE", "")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        if api_type == "azure":
            self.api_base = os.getenv("AZURE_OPENAI_API_BASE", "")
            self.api_version = "2024-08-01-preview"
            self.client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        else:
            self.client = OpenAI(api_key=self.api_key)
        
        self.deployment_name = "text-embedding-3-large"
        
        logger.info("OpenAI3LargeEmbedder initialized successfully")
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        logger.debug(f"[OpenAI3LargeEmbedder] Embedding {len(texts)} texts using {self.deployment_name}")
        try:
            response = self.client.embeddings.create(
                model=self.deployment_name,
                input=texts,
            )
            logger.info(f"Successfully embedded {len(texts)} texts")
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"[OpenAI3LargeEmbedder] Embedding failed: {e}", exc_info=True)
            raise RuntimeError(f"Embedding failed: {e}")
