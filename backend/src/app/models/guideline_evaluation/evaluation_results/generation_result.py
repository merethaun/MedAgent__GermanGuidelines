from datetime import datetime, timezone
from typing import Optional, Literal, List

from pydantic import BaseModel, Field

from app.utils.knowledge.mongodb_object_id import PyObjectId
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ManualEvaluator(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    name: str = Field(description="The name of the evaluator")


class EvaluationMetrics(BaseModel):
    target: str = Field(description="Target component being evaluated")
    metric_title: str = Field(description="Title of the evaluation metric (specifying what is evaluated on target)")
    manual: bool = Field(description="Whether evaluation was performed manually or automatically")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of creation")
    note: Optional[str] = Field(default=None)


class EvaluationRetrieval(EvaluationMetrics):
    target: str = Field(default="Retriever")
    metric_title: str = Field(default="Retrieval performance")
    manual: bool = Field(default=False)
    recall: Optional[float] = Field(
        default=None, description="Proportion of relevant (expected) retrievals that were retrieved",
    )
    precision: Optional[float] = Field(
        default=None, description="Proportion of retrieved sections that were relevant (expected)",
    )
    f1: Optional[float] = Field(default=None, description="Harmonic mean of precision and recall scores")
    retrieval_latency: Optional[float] = Field(default=None, description="Time taken for retrieval in seconds")


class EvaluationAccuracy(EvaluationMetrics):
    target: str = Field(default="System")
    metric_title: str = Field(default="Accuracy (automatic)")
    manual: bool = Field(default=False)
    bleu_score: Optional[float] = Field(
        default=None, description="BLEU score measuring n-gram overlap with correct answer",
    )
    rouge_1_score: Optional[float] = Field(
        default=None, description="ROUGE-1 score measuring unigram overlap with correct answer",
    )
    rouge_l_score: Optional[float] = Field(
        default=None,
        description="ROUGE-L score measuring longest common subsequence between generated and correct answer",
    )
    meteor_score: Optional[float] = Field(default=None, description="METEOR score considering synonyms and paraphrases")
    cosine_similarity: Optional[float] = Field(
        default=None, description="Cosine similarity between embeddings of generated and correct answer",
    )
    euclidean_distance: Optional[float] = Field(
        default=None, description="Euclidean distance between embeddings of generated and correct answer",
    )
    bert_score_f1: Optional[float] = Field(default=None, description="BERTscore measuring similarity to correct answer (F1, set to German)")
    bert_score_precision: Optional[float] = Field(
        default=None, description="BERTscore measuring similarity to correct answer (precision, set to German)",
    )
    bert_score_recall: Optional[float] = Field(default=None, description="BERTscore measuring similarity to correct answer (recall, set to German)")
    gpt_likert_similarity: Optional[float] = Field(
        default=None, description="Numerical similarity score similar to Likert scale from [1, 5]",
    )


class EvaluationResponseLatency(EvaluationMetrics):
    target: str = Field(default="System")
    metric_title: str = Field(default="Response latency")
    manual: bool = Field(default=False)
    response_latency: Optional[float] = Field(
        default=None, description="Total response time (whole workflow) in seconds",
    )


class EvaluationCorrectness(EvaluationMetrics):
    target: str = Field(default="System")
    metric_title: str = Field(default="Correctness")
    manual: bool = Field(default=True)
    evaluator: PyObjectId = Field(description="Creator of this evaluation (MongoDB document ID)")
    correctness_score: Optional[Literal[1, 2, 3, 4, 5]] = Field(
        default=None, description="Likert scale rating of overall correctness",
    )
    count_factual_conflicts: Optional[int] = Field(
        default=None, description="Hallucinations: number of factual conflicts",
    )
    count_input_conflicts: Optional[int] = Field(
        default=None, description="Hallucinations: number of conflicts to the user input",
    )
    count_context_conflicts: Optional[int] = Field(
        default=None, description="Hallucinations: number of conflicts to the context (retrieval / history)",
    )


class EvaluationFactuality(EvaluationMetrics):
    target: str = Field(default="Generator")
    metric_title: str = Field(default="Factuality")
    manual: bool = Field(default=True)
    evaluator: PyObjectId = Field(description="Creator of this evaluation (MongoDB document ID)")
    fact_count_overall: Optional[int] = Field(default=None, description="Number of facts in generated answer")
    fact_count_backed: Optional[int] = Field(
        default=None, description="Number of facts backed by presented retrieval in generated answer",
    )
    factuality_score: Optional[float] = Field(
        default=None, description="Overall factuality score between 0 and 1 (fact_count_backed / fact_count_overall)",
    )


class GenerationResultRun(BaseModel):
    workflow_system_id: PyObjectId = Field(description="Related / utilized workflow system (MongoDB document ID)")
    name: str = Field(description="Name of run for generating evaluation results (be careful to name unique)")
    
    def __hash__(self):
        return hash((self.workflow_system_id, self.name))
    
    def __eq__(self, other):
        correct_type = isinstance(other, GenerationResultRun)
        correct_config = self.workflow_system_id == other.workflow_system_id and self.name == other.name
        return correct_type and correct_config


class AutomaticEvaluation(BaseModel):
    retrieval_evaluation: "EvaluationRetrieval" = Field(default=EvaluationRetrieval())
    accuracy_evaluation: "EvaluationAccuracy" = Field(default=EvaluationAccuracy())
    latency_evaluation: "EvaluationResponseLatency" = Field(default=EvaluationResponseLatency())


class GenerationResult(BaseModel):
    """
    Main model for storing evaluation (generation) results.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    generation_run: GenerationResultRun = Field(description="Grouping for one generation running")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of creation",
    )
    
    related_question: PyObjectId = Field(description="Related question used as user input (MongoDB document ID)")
    related_chat: PyObjectId = Field(description="Related chat capturing generation result (MongoDB document ID)")
    
    automatic_evaluation: "AutomaticEvaluation" = Field(default=AutomaticEvaluation())
    
    requires_manual_evaluation: bool = Field(default=False)
    correctness_evaluations: "List[EvaluationCorrectness]" = Field(default=[], description="All (manual) correctness evaluations")
    factuality_evaluations: "List[EvaluationFactuality]" = Field(default=[], description="All (manual) factuality evaluations")
