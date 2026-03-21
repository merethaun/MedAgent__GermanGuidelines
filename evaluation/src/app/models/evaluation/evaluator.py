from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from app.models.common.py_object_id import PyObjectId


class EvaluatorProfile(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    sub: str
    username: Optional[str] = None
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )
