from typing import List, Dict, Callable

from app.utils.logger import setup_logger
from app.utils.vectorizer import AbstractVectorizer, BAAILLMEmbedder, OpenAI3LargeEmbedder, BAAIBilingualGeneralEmbedderM3
from app.utils.vectorizer.baai_bge_reranker_large import BAAIBilingualGeneralRerankerLarge

logger = setup_logger(__name__)


class VectorizerService:
    """
    General service to use vectorizers (text to vector embedding).
    """
    
    def __init__(self):
        self.vectorizers: Dict[str, Callable[[], AbstractVectorizer]] = {
            "text-embedding-3-large": OpenAI3LargeEmbedder,
            "baai-llm-embedder": BAAILLMEmbedder,
            "baai-bge-m3": BAAIBilingualGeneralEmbedderM3,
            "baai-bge-reranker-large": BAAIBilingualGeneralRerankerLarge,
        }
        
        self.instances: Dict[str, AbstractVectorizer] = {
            name: constructor() for name, constructor in self.vectorizers.items()
        }
    
    def list_available_vectorizers(self) -> List[str]:
        return list(self.instances.keys())
    
    def vectorize(self, texts: List[str], provider: str) -> List[List[float]]:
        logger.debug(f"Vectorizing {len(texts)} texts using provider: {provider}")
        if provider not in self.instances:
            logger.error(f"Unsupported vectorizer provider: {provider}")
            raise ValueError(f"Unsupported vectorizer provider: {provider}")
        
        vectorizer = self.instances[provider]
        return vectorizer.embed_texts(texts)
