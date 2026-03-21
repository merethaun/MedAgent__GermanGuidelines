from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.common.py_object_id import PyObjectId
from app.models.evaluation.dataset import ExpectedRetrievalSnippet, QuestionClassification
from app.models.evaluation.metrics import AutomaticMetrics

SampleSourceType = Literal["question_group_batch", "chat_snapshot"]
RunStatus = Literal["queued", "running", "completed", "failed", "partial"]
SampleStatus = Literal["queued", "running", "completed", "failed"]
ManualReviewMode = Literal["none", "open", "assigned", "mixed"]


class ManualReviewAssignment(BaseModel):
    question_id: Optional[str] = None
    evaluator_sub: str
    evaluator_username: Optional[str] = None


class LLMSettingsOverride(BaseModel):
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    timeout_s: Optional[int] = Field(default=None, ge=1)
    seed: Optional[int] = None
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    extra_body: Dict[str, Any] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any(
            [
                self.model,
                self.api_key,
                self.base_url,
                self.temperature is not None,
                self.top_p is not None,
                self.max_tokens is not None,
                self.timeout_s is not None,
                self.seed is not None,
                bool(self.extra_headers),
                bool(self.extra_body),
            ],
        )


class EvaluationRunCreateRequest(BaseModel):
    name: str
    workflow_system_id: str
    source_type: SampleSourceType
    question_group_id: Optional[str] = None
    source_chat_id: Optional[str] = None
    source_interaction_index: Optional[int] = Field(default=None, ge=0)
    manual_review_mode: ManualReviewMode = "open"
    assigned_evaluator_sub: Optional[str] = None
    assigned_evaluator_username: Optional[str] = None
    manual_review_assignments: List[ManualReviewAssignment] = Field(default_factory=list)
    runtime_llm_settings: Optional[LLMSettingsOverride] = None

    @model_validator(mode="after")
    def validate_shape(self) -> "EvaluationRunCreateRequest":
        if self.source_type == "question_group_batch" and not self.question_group_id:
            raise ValueError("question_group_id is required for question_group_batch runs")
        if self.source_type == "chat_snapshot":
            if not self.source_chat_id:
                raise ValueError("source_chat_id is required for chat_snapshot runs")
            if self.source_interaction_index is None:
                raise ValueError("source_interaction_index is required for chat_snapshot runs")
        if self.manual_review_mode == "assigned" and not self.assigned_evaluator_sub:
            raise ValueError("assigned_evaluator_sub is required for assigned manual review mode")
        if self.runtime_llm_settings is not None and self.runtime_llm_settings.is_empty():
            self.runtime_llm_settings = None
        return self


class EvaluationRun(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    name: str
    workflow_system_id: str
    workflow_name: Optional[str] = None
    source_type: SampleSourceType
    status: RunStatus = "queued"
    question_group_id: Optional[str] = None
    question_group_name: Optional[str] = None
    source_chat_id: Optional[str] = None
    source_interaction_index: Optional[int] = None
    manual_review_mode: ManualReviewMode = "open"
    assigned_evaluator_sub: Optional[str] = None
    assigned_evaluator_username: Optional[str] = None
    manual_review_assignments: List[ManualReviewAssignment] = Field(default_factory=list)
    created_by_sub: str
    created_by_username: Optional[str] = None
    total_samples: int = 0
    processed_samples: int = 0
    failed_samples: int = 0
    open_tasks: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )


class EvaluationSample(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    run_id: PyObjectId
    source_type: SampleSourceType
    status: SampleStatus = "queued"
    source_question_id: Optional[str] = None
    source_question_group_id: Optional[str] = None
    source_chat_id: Optional[str] = None
    source_interaction_index: Optional[int] = None
    workflow_system_id: Optional[str] = None
    workflow_name: Optional[str] = None
    question_text: Optional[str] = None
    question_classification: Optional[QuestionClassification] = None
    expected_answer: Optional[str] = None
    expected_retrieval: List[ExpectedRetrievalSnippet] = Field(default_factory=list)
    backend_chat_id: Optional[str] = None
    backend_interaction_index: Optional[int] = None
    answer_text: Optional[str] = None
    retrieval_output: List[Dict[str, Any]] = Field(default_factory=list)
    response_latency: Optional[float] = None
    retrieval_latency: Optional[float] = None
    workflow_execution: List[Dict[str, Any]] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    automatic_metrics: AutomaticMetrics = AutomaticMetrics()
    manual_review_task_id: Optional[str] = None
    user_feedback_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )
