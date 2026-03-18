from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge.guideline.guideline_reference import GuidelineReference
from app.models.tools.llm_interaction import LLMSettings


class GuidelineContextFilterMethod(str, Enum):
    SCORE = "score"
    CROSS_ENCODER = "cross_encoder"
    LLM = "llm"


class GuidelineContextFilterKind(str, Enum):
    DEDUPLICATE = "deduplicate"
    RELEVANCE = "relevance"


class RetrievalPropertySelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ...,
        description=(
            "Property path used to build the filter input per item. "
            "Supports reference fields such as 'content', 'heading_path', 'associated_keywords', "
            "or dotted paths inside the reference model."
        ),
    )
    label: Optional[str] = Field(default=None, description="Optional label used in the serialized item text.")
    include_label: bool = Field(default=True, description="Whether the label should be included.")
    max_chars: Optional[int] = Field(default=None, ge=1, description="Optional per-property truncation limit.")


class GuidelineContextFilterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: GuidelineContextFilterKind = Field(default=GuidelineContextFilterKind.RELEVANCE)
    method: GuidelineContextFilterMethod = Field(default=GuidelineContextFilterMethod.SCORE)
    properties: List[RetrievalPropertySelector] = Field(
        default_factory=lambda: [RetrievalPropertySelector(path="retrieval", label="text")],
        min_length=1,
    )
    joiner: str = Field(default="\n")
    include_empty_properties: bool = Field(default=False)
    sort_by_score: bool = Field(default=True)
    keep_top_k: Optional[int] = Field(default=None, ge=1, le=100)
    minimum_score: Optional[float] = Field(default=None)

    score_field: str = Field(default="order")

    cross_encoder_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    cross_encoder_max_length: int = Field(default=512, ge=16, le=4096)

    llm_settings: Optional[LLMSettings] = Field(default=None)
    llm_system_prompt: Optional[str] = Field(default=None)
    llm_batch_size: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Optional number of references to judge per LLM call. If omitted, all references are judged in one batch.",
    )

    deduplicate_use_normalized_text: bool = Field(default=True)
    deduplicate_keep_strategy: str = Field(
        default="highest_score",
        description="How to pick the representative item for a duplicate group. Supported: 'highest_score', 'first'.",
    )

    @model_validator(mode="after")
    def validate_method_specific_settings(self) -> "GuidelineContextFilterSettings":
        if self.kind == GuidelineContextFilterKind.RELEVANCE and self.method == GuidelineContextFilterMethod.LLM and self.llm_settings is None:
            raise ValueError("llm_settings are required when method='llm'.")
        if self.deduplicate_keep_strategy not in {"highest_score", "first"}:
            raise ValueError("deduplicate_keep_strategy must be one of: 'highest_score', 'first'.")
        return self


class GuidelineContextFilterDecision(BaseModel):
    index: int
    kept: bool
    score: Optional[float] = None
    reason: Optional[str] = None
    serialized_item: Optional[str] = None
    reference_id: Optional[str] = None
    source_id: Optional[str] = None


class GuidelineContextFilterRequest(BaseModel):
    filter_input: str = Field(..., description="The query, response, or other filter input.")
    references: List[GuidelineReference]
    settings: GuidelineContextFilterSettings


class GuidelineContextFilterResponse(BaseModel):
    kind: GuidelineContextFilterKind
    method: GuidelineContextFilterMethod
    filter_input: str
    kept_references: List[GuidelineReference]
    dropped_references: List[GuidelineReference]
    decisions: List[GuidelineContextFilterDecision]
    latency: float
