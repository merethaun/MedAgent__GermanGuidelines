from typing import List

from pydantic import BaseModel, Field


class GuidelineValidationResult(BaseModel):
    is_valid: bool = Field(
        default=True, description="Indicates if the entity is valid (no blocking errors).", examples=[False],
    )
    is_complete: bool = Field(
        default=True, description="Indicates if the entity is complete (no missing recommended fields).",
        examples=[False],
    )
    errors: List[str] = Field(
        default_factory=list, description="List of critical validation errors that block acceptance.",
        examples=[["File path does not exist.", "Page count mismatch."]],
    )
    warnings: List[str] = Field(
        default_factory=list, description="List of non-blocking validation warnings.",
        examples=[
            ["No keywords provided.", "Missing optional file path."],
            ["File path exists, but page count is not set."],
        ],
    )
    
    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.is_valid = False
        self.is_complete = False
    
    def add_warning(self, message: str) -> None:
        self.warnings.append(message)
        self.is_complete = False
