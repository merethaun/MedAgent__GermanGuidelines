class GuidelineReferenceChunkingError(ValueError):
    """Base error for reference chunking operations."""


class InvalidChunkingConfigurationError(GuidelineReferenceChunkingError):
    """Raised when the selected chunking strategy is configured incorrectly."""


class NarrativeReferenceNotFoundError(GuidelineReferenceChunkingError):
    """Raised when a chunking run has no narrative text references available to process."""


class ChunkingUpdateSourceEmptyError(GuidelineReferenceChunkingError):
    """Raised when a guideline-specific update has no source references to copy."""
