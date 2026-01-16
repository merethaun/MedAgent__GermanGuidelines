from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

from app.utils.knowledge.mongodb_object_id import PyObjectId
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class QuestionGroup(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    group_name: str = Field(description="The name of the question group (e.g., test, final, ...)")


class QuestionClassification(BaseModel):
    """
    Classification model for categorizing questions based on their complexity and content type.
    Used to organize and filter questions in the evaluation dataset.
    """
    super_class: str = Field(..., description="Super class of the question", examples=["Simple", "Complex", "Negative"])
    sub_class: str = Field(
        ..., description="Sub class of the question",
        examples=["Text", "Recommendation", "Multiple sections", "Outside medicine"],
    )
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"super_class": "Simple", "sub_class": "Text"},
                {"super_class": "Simple", "sub_class": "Figure"},
                {"super_class": "Simple", "sub_class": "Table"},
                {"super_class": "Simple", "sub_class": "Recommendation"},
                {"super_class": "Complex", "sub_class": "Synonym"},
                {"super_class": "Complex", "sub_class": "Multiple sections"},
                {"super_class": "Complex", "sub_class": "Multiple guidelines"},
                {"super_class": "Complex", "sub_class": "Substeps"},
                {"super_class": "Negative", "sub_class": "Outside medicine"},
                {"super_class": "Negative", "sub_class": "Outside OMS"},
                {"super_class": "Negative", "sub_class": "Outside guidelines"},
                {"super_class": "Negative", "sub_class": "Patient-specific"},
                {"super_class": "Negative", "sub_class": "Broken input"},
                {"super_class": "Negative", "sub_class": "False assumption"},
            ],
        },
    )


class QuestionEntry(BaseModel):
    """
    Main model for storing evaluation questions along with their expected answers and guideline references.
    Used to assess information retrieval and question answering quality.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    question_group: PyObjectId = Field(description="Question group (MongoDB document ID)")
    question: str = Field(
        description="The question text to be answered", examples=[
            "What are the indications for wisdom tooth removal?",
            "When should a 3D imaging be performed before wisdom tooth extraction?",
        ],
    )
    classification: QuestionClassification = Field(description="Classification of the question type and complexity")
    correct_answer: str = Field(
        description="The expected correct answer to the question", examples=[
            "Wisdom teeth should be removed when there is insufficient space for proper eruption.",
            "3D imaging should be performed when there are signs of nerve proximity.",
        ],
    )
    expected_retrieval: List[PyObjectId] = Field(
        description="List of guideline references that contain information relevant to answering the question",
        default_factory=list,
    )
    note: Optional[str] = Field(default=None, description="Additional notes or comments about the question")
