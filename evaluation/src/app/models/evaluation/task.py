from datetime import datetime, timezone
from typing import Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.common.py_object_id import PyObjectId

TaskStatus = Literal["open", "claimed", "completed"]
TaskAssignmentMode = Literal["open", "assigned"]


class ManualReviewSubmission(BaseModel):
    correctness_score: Optional[int] = Field(default=None, ge=1, le=5)
    factuality_score: Optional[int] = Field(default=None, ge=1, le=5)
    count_factual_conflicts: Optional[int] = Field(default=None, ge=0)
    count_input_conflicts: Optional[int] = Field(default=None, ge=0)
    count_context_conflicts: Optional[int] = Field(default=None, ge=0)
    fact_count_overall: Optional[int] = Field(default=None, ge=0)
    fact_count_backed: Optional[int] = Field(default=None, ge=0)
    note: Optional[str] = None

    @field_validator("fact_count_backed")
    @classmethod
    def validate_backed_facts(cls, value: Optional[int], info):
        overall = info.data.get("fact_count_overall")
        if value is not None and overall is not None and value > overall:
            raise ValueError("fact_count_backed must not exceed fact_count_overall")
        return value


class ManualReviewResult(ManualReviewSubmission):
    reviewer_sub: str
    reviewer_username: Optional[str] = None
    factuality_ratio: Optional[float] = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ManualReviewTask(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    run_id: PyObjectId
    sample_id: PyObjectId
    status: TaskStatus = "open"
    assignment_mode: TaskAssignmentMode = "open"
    assigned_evaluator_sub: Optional[str] = None
    assigned_evaluator_username: Optional[str] = None
    claimed_by_sub: Optional[str] = None
    claimed_by_username: Optional[str] = None
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    review: Optional[ManualReviewResult] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )
