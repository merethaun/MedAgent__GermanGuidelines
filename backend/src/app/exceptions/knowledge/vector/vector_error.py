class VectorizerNotFoundError(ValueError):
    """Raised when a requested vectorizer provider is unknown."""


class VectorizerNotAvailableError(RuntimeError):
    """Raised when a vectorizer exists but cannot be used in the current environment."""


class VectorCollectionNotFoundError(ValueError):
    """Raised when Weaviate collection metadata cannot be found."""
