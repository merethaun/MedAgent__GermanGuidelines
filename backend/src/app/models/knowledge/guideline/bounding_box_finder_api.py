from typing import Optional

from pydantic import BaseModel, Field


class BoundingBoxFinderRequest(BaseModel):
    guideline_id: str = Field(...)
    text: str = Field(..., min_length=1)
    
    start_page: Optional[int] = Field(default=None)
    end_page: Optional[int] = Field(default=None)
