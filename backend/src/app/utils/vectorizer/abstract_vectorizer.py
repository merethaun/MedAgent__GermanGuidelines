from abc import ABC, abstractmethod
from typing import List


class AbstractVectorizer(ABC):
    """
    Abstract base class for all vectorizers.
    """
    
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Convert a list of texts into a list of embedding vectors.
        """
        pass
