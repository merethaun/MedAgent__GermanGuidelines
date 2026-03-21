from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.common.py_object_id import PyObjectId
from app.models.knowledge.guideline.guideline_reference import GuidelineReference


class RetrievalResult(BaseModel):
    source_id: Optional[PyObjectId] = Field(default=None, description="MongoDB ID for guideline entry")
    retrieval: Optional[str] = Field(default=None, description="Retrieval result (as text)")
    
    reference_id: Optional[PyObjectId] = Field(default=None, description="MongoDB ID for reference entry")
    weaviate_uuid: Optional[str] = Field(default=None, description="Weaviate object UUID for this hit")
    weaviate_score: Optional[float] = Field(default=None, description="Weaviate search score for this hit")
    weaviate_distance: Optional[float] = Field(default=None, description="Weaviate vector distance for this hit")
    weaviate_properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Full property payload returned by Weaviate for this hit.",
    )
    
    @model_validator(mode='after')
    def validate_either_source_or_reference(self) -> 'RetrievalResult':
        if (self.source_id is None or self.retrieval is None) and self.reference_id is None:
            raise ValueError("Must provide at least either reference id, or source id AND retrieval")
        return self
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )


RetrievedWorkflowItem = Union[RetrievalResult, GuidelineReference]


def sanitize(obj):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize(v) for v in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    return obj


class WorkflowComponentExecutionResult(BaseModel):
    component_id: str
    execution_order: int
    input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input to the component (can be derived when comparing output from previous components) -> too expensive to store",
    )
    output: Dict[str, Any] = Field(default_factory=dict, description="Output from the component (that the component actually created)")
    
    @field_validator("input", "output", mode="before")
    @classmethod
    def sanitize_nested(cls, v):
        return sanitize(v)
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


class RenameChatRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class PoseQuestionRequest(BaseModel):
    user_input: str = Field(..., min_length=1, description="User input / question")
    runtime_llm_settings: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional per-request LLM settings override used during workflow execution.",
    )


class ChatInteraction(BaseModel):
    user_input: str
    time_question_input: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generator_output: Optional[str] = Field(default=None)
    time_response_output: Optional[datetime] = Field(default=None)
    retrieval_output: List[RetrievedWorkflowItem] = Field(default_factory=list)
    retrieval_latency: Optional[float] = Field(default=None)
    
    workflow_execution: List[WorkflowComponentExecutionResult] = Field(default_factory=list)


class Chat(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    name: Optional[str] = Field(default=None, description="Chat name, ideally including brief description")
    workflow_system_id: PyObjectId = Field(description="Related / utilized workflow system (MongoDB document ID)")
    username: str = Field(default="No user", description="Username of the sender")
    interactions: List[ChatInteraction] = Field(default_factory=list)
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )
