class GuidelineReferenceGroupNotFoundError(ValueError):
    """Raised when a guideline reference group cannot be found (or the id is invalid)."""


class GuidelineReferenceNotFoundError(ValueError):
    """Raised when a guideline reference entry cannot be found (or the id is invalid)."""
