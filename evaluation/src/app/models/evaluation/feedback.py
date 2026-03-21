from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from app.models.common.py_object_id import PyObjectId


class AnswerFeedbackCreateRequest(BaseModel):
    chat_id: str
    interaction_index: int = Field(ge=0)
    helpful: Optional[bool] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = None


class AnswerFeedbackEntry(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    user_sub: str
    username: Optional[str] = None
    chat_id: str
    interaction_index: int
    helpful: Optional[bool] = None
    rating: Optional[int] = None
    comment: Optional[str] = None
    question_text: Optional[str] = None
    answer_text: Optional[str] = None
    workflow_system_id: Optional[str] = None
    retrieval_output: list[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )
