from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Tuple

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.models.common.py_object_id import PyObjectId


class QuestionSuperClass(str, Enum):
    SIMPLE = "simple"
    NEGATIVE = "negative"
    COMPLEX = "complex"


class SimpleQuestionSubClass(str, Enum):
    TEXT = "text"
    RECOMMENDATION = "recommendation"
    TABLE = "table"
    STATEMENT = "statement"
    IMAGE = "image"


class ComplexQuestionSubClass(str, Enum):
    MULTIPLE_GUIDELINES = "multiple_guidelines"
    MULTIPLE_SECTIONS_SAME_GUIDELINE = "multiple_sections_same_guideline"
    SYNONYM = "synonym"
    MULTI_STEP_REASONING = "multi_step_reasoning"


class NegativeQuestionSubClass(str, Enum):
    OUTSIDE_MEDICINE = "outside_medicine"
    OUTSIDE_OMFS = "outside_omfs"
    OUTSIDE_GUIDELINES = "outside_guidelines"
    MALFORMED = "malformed"
    PATIENT_SPECIFIC = "patient_specific"
    FALSE_ASSUMPTION = "false_assumption"


QUESTION_SUBCLASS_OPTIONS = {
    QuestionSuperClass.SIMPLE: {item.value for item in SimpleQuestionSubClass},
    QuestionSuperClass.COMPLEX: {item.value for item in ComplexQuestionSubClass},
    QuestionSuperClass.NEGATIVE: {item.value for item in NegativeQuestionSubClass},
}

QUESTION_SUPERCLASS_ALIASES = {
    "simple": QuestionSuperClass.SIMPLE.value,
    "negative": QuestionSuperClass.NEGATIVE.value,
    "complex": QuestionSuperClass.COMPLEX.value,
}

QUESTION_SUBCLASS_ALIASES = {
    "text": SimpleQuestionSubClass.TEXT.value,
    "recommendation": SimpleQuestionSubClass.RECOMMENDATION.value,
    "recommendatoin": SimpleQuestionSubClass.RECOMMENDATION.value,
    "table": SimpleQuestionSubClass.TABLE.value,
    "statement": SimpleQuestionSubClass.STATEMENT.value,
    "image": SimpleQuestionSubClass.IMAGE.value,
    "multiple_guidelines": ComplexQuestionSubClass.MULTIPLE_GUIDELINES.value,
    "multiple guidelines": ComplexQuestionSubClass.MULTIPLE_GUIDELINES.value,
    "multiple_sections_same_guideline": ComplexQuestionSubClass.MULTIPLE_SECTIONS_SAME_GUIDELINE.value,
    "multiple sections same guideline": ComplexQuestionSubClass.MULTIPLE_SECTIONS_SAME_GUIDELINE.value,
    "multiple sections": ComplexQuestionSubClass.MULTIPLE_SECTIONS_SAME_GUIDELINE.value,
    "multiple sections same guidleine": ComplexQuestionSubClass.MULTIPLE_SECTIONS_SAME_GUIDELINE.value,
    "same guideline multiple sections": ComplexQuestionSubClass.MULTIPLE_SECTIONS_SAME_GUIDELINE.value,
    "synonym": ComplexQuestionSubClass.SYNONYM.value,
    "multi_step_reasoning": ComplexQuestionSubClass.MULTI_STEP_REASONING.value,
    "multi step reasoning": ComplexQuestionSubClass.MULTI_STEP_REASONING.value,
    "multi-step reasoning": ComplexQuestionSubClass.MULTI_STEP_REASONING.value,
    "multi step resoning": ComplexQuestionSubClass.MULTI_STEP_REASONING.value,
    "muliiti step resoning": ComplexQuestionSubClass.MULTI_STEP_REASONING.value,
    "outside_medicine": NegativeQuestionSubClass.OUTSIDE_MEDICINE.value,
    "outside medicine": NegativeQuestionSubClass.OUTSIDE_MEDICINE.value,
    "outside_omfs": NegativeQuestionSubClass.OUTSIDE_OMFS.value,
    "outside omfs": NegativeQuestionSubClass.OUTSIDE_OMFS.value,
    "outside_guidelines": NegativeQuestionSubClass.OUTSIDE_GUIDELINES.value,
    "outside guidelines": NegativeQuestionSubClass.OUTSIDE_GUIDELINES.value,
    "malformed": NegativeQuestionSubClass.MALFORMED.value,
    "mal formed": NegativeQuestionSubClass.MALFORMED.value,
    "mal-formed": NegativeQuestionSubClass.MALFORMED.value,
    "patient_specific": NegativeQuestionSubClass.PATIENT_SPECIFIC.value,
    "patient specific": NegativeQuestionSubClass.PATIENT_SPECIFIC.value,
}


def _normalize_key(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("/", " ").replace("_", " ").replace("-", " ").split())


class QuestionGroup(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )


class QuestionClassification(BaseModel):
    super_class: QuestionSuperClass
    sub_class: str = Field(min_length=1)
    
    @field_validator("super_class", mode="before")
    @classmethod
    def normalize_super_class(cls, value: str | QuestionSuperClass) -> str:
        if isinstance(value, QuestionSuperClass):
            return value.value
        normalized = QUESTION_SUPERCLASS_ALIASES.get(_normalize_key(str(value)))
        if normalized is None:
            raise ValueError("super_class must be one of: simple, negative, complex")
        return normalized
    
    @field_validator("sub_class", mode="before")
    @classmethod
    def normalize_sub_class(cls, value: str) -> str:
        normalized = QUESTION_SUBCLASS_ALIASES.get(_normalize_key(str(value)))
        if normalized is None:
            allowed = sorted({item for items in QUESTION_SUBCLASS_OPTIONS.values() for item in items})
            raise ValueError(f"sub_class must be one of: {', '.join(allowed)}")
        return normalized
    
    @model_validator(mode="after")
    def validate_combination(self) -> "QuestionClassification":
        allowed = QUESTION_SUBCLASS_OPTIONS[self.super_class]
        if self.sub_class not in allowed:
            raise ValueError(
                f"sub_class '{self.sub_class}' is not valid for super_class '{self.super_class.value}'",
            )
        return self


class EvaluationReferenceType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    RECOMMENDATION = "recommendation"
    STATEMENT = "statement"
    METADATA = "metadata"


class BoundingBox(BaseModel):
    page: int = Field(ge=1)
    positions: Tuple[float, float, float, float]
    
    @field_validator("positions", mode="before")
    @classmethod
    def coerce_positions(cls, value):
        if isinstance(value, list) and len(value) == 4:
            return tuple(value)
        return value
    
    @field_serializer("positions")
    def serialize_positions(self, positions: Tuple[float, float, float, float]) -> List[float]:
        return list(positions)


class ExpectedRetrievalSnippet(BaseModel):
    guideline_source: Optional[str] = Field(default=None, description="Publication or PDF source URL for the guideline")
    guideline_title: Optional[str] = Field(default=None)
    bounding_boxes: List[BoundingBox] = Field(default_factory=list)
    reference_type: Optional[EvaluationReferenceType] = Field(default=None)
    retrieval_text: str = Field(default="", description="Expected retrieval text or short excerpt")


class QuestionEntry(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    question_group_id: PyObjectId = Field(description="Related question group")
    question: str
    classification: QuestionClassification
    correct_answer: Optional[str] = None
    expected_retrieval: List[ExpectedRetrievalSnippet] = Field(default_factory=list)
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )
