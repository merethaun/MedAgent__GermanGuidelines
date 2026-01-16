from typing import List, Union, Dict, Any

from pydantic import BaseModel

from app.models.guideline_evaluation.question_dataset.question_entry import QuestionClassification, QuestionEntry
from app.utils.knowledge.mongodb_object_id import PyObjectId
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ParseResultResponse(BaseModel):
    inserted_entries: List[QuestionEntry]
    failed_entries: List[Dict[str, Any]]


class ExpectedAnswerParserResult(BaseModel):
    """
    Store information parsed form csv file to insert into dataset for the expected retrieval
    """
    guideline_id: Union[str, PyObjectId]
    page: int
    contained_text: str


class QuestionParserResult(BaseModel):
    """
    Store information parsed form csv file to insert into dataset
    """
    question: str
    classification: QuestionClassification
    correct_answer: str
    note: str
    expected_retrieval: List[ExpectedAnswerParserResult]
