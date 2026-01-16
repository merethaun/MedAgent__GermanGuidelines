from typing import TYPE_CHECKING, Literal, Optional

from app.models.guideline_evaluation.evaluation_results.generation_result import (
    GenerationResult, EvaluationCorrectness, EvaluationFactuality,
)
from app.utils.knowledge.mongodb_object_id import PyObjectId
from app.utils.logger import setup_logger

if TYPE_CHECKING:
    from app.services.guideline_evaluation.evaluation_results import ResultGenerationService

logger = setup_logger(__name__)


class ManualEvaluationService:
    """
    Service to insert manually created evaluation scores
    """
    
    def __init__(self, generated_results_service: "ResultGenerationService"):
        self.generated_results_service = generated_results_service
    
    def write_correctness_evaluation(
            self, evaluator_id: PyObjectId, generation_result: GenerationResult, likert_correctness_score: int,
            counter_factual_conflicts: Optional[int], counter_input_conflicts: Optional[int],
            counter_context_conflicts: Optional[int], note: Optional[str] = None,
    ) -> GenerationResult:
        logger.debug(f"Writing correctness evaluation for generation result {generation_result.id}")
        
        def _transform_to_literal(value: int) -> Literal[1, 2, 3, 4, 5]:
            if value in (1, 2, 3, 4, 5):
                return value
            else:
                raise ValueError(f"Invalid correctness score value ({value} not in [1, 2, 3, 4, 5])")
        
        correctness_evaluation = EvaluationCorrectness(
            evaluator=evaluator_id,
            correctness_score=_transform_to_literal(likert_correctness_score),
            count_factual_conflicts=counter_factual_conflicts,
            count_input_conflicts=counter_input_conflicts,
            count_context_conflicts=counter_context_conflicts,
            note=note,
        )
        
        corr_evals = generation_result.correctness_evaluations
        if any([str(c_eval.evaluator) == str(evaluator_id) for c_eval in corr_evals]):
            corr_evals = [
                c_eval if str(c_eval.evaluator) != str(evaluator_id) else correctness_evaluation
                for c_eval in corr_evals
            ]
        else:
            corr_evals.append(correctness_evaluation)
        
        logger.debug(f"Constructed correctness evaluation: {correctness_evaluation}")
        
        updated_result = self.generated_results_service.update_generation_result_entry(
            gen_result_entry_id=generation_result.id,
            update_data={
                "correctness_evaluations": corr_evals,
            },
        )
        
        logger.debug(f"Updated generation result with correctness evaluation")
        
        return updated_result
    
    def write_factuality_evaluation(
            self, evaluator_id: PyObjectId, generation_result: GenerationResult, counter_facts_overall: int, counter_facts_backed: int,
            note: Optional[str] = None,
    ) -> GenerationResult:
        logger.debug(f"Writing factuality evaluation for generation result {generation_result.id}")
        
        if counter_facts_backed > counter_facts_overall:
            raise ValueError(
                f"Invalid fact counts provided: overall facts {counter_facts_overall} !> "
                f"facts backed by retrieval {counter_facts_backed}",
            )
        if counter_facts_overall < 0 or counter_facts_backed < 0:
            raise ValueError(
                f"Invalid fact counts provided: both must be positive, but facts overall={counter_facts_overall}"
                f"facts backed={counter_facts_backed}",
            )
        
        factuality_score = counter_facts_backed / counter_facts_overall if counter_facts_overall > 0 else 0.0
        logger.info(
            f"Calculated factuality score: {factuality_score:.2f} (backed: {counter_facts_backed}, "
            f"overall: {counter_facts_overall})",
        )
        
        factuality_evaluation = EvaluationFactuality(
            evaluator=evaluator_id,
            fact_count_overall=counter_facts_overall,
            fact_count_backed=counter_facts_backed,
            factuality_score=factuality_score,
            note=note,
        )
        
        fact_evals = generation_result.factuality_evaluations
        if any([str(f_eval.evaluator) == str(evaluator_id) for f_eval in fact_evals]):
            fact_evals = [
                f_eval if str(f_eval.evaluator) != str(evaluator_id) else factuality_evaluation
                for f_eval in fact_evals
            ]
        else:
            fact_evals.append(factuality_evaluation)
        logger.debug(f"Constructed factuality evaluation: {factuality_evaluation}")
        
        updated_result = self.generated_results_service.update_generation_result_entry(
            gen_result_entry_id=generation_result.id,
            update_data={
                "factuality_evaluations": fact_evals,
            },
        )
        
        logger.debug("Updated generation result with factuality evaluation")
        
        return updated_result
