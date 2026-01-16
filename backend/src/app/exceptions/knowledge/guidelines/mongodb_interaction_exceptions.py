class GuidelineNotFoundError(Exception):
    """Raised when a guideline could not be found in the database."""
    
    def __init__(self, guideline_id: str):
        self.guideline_id = guideline_id
        self.message = f"Guideline with ID {guideline_id} not found."
        super().__init__(self.message)
