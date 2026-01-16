from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import conint

from app.models.guideline_evaluation.evaluation_results.generation_result import GenerationResult, GenerationResultRun, ManualEvaluator
from app.services.guideline_evaluation.evaluation_results import (
    ResultGenerationService, AutomaticEvaluationService, ManualEvaluationService,
)
from app.services.system import WorkflowSystemStorageService
from app.utils.logger import setup_logger
from app.utils.service_creators import (
    get_result_generation_service, get_workflow_storage, get_automatic_evaluation_service, get_manual_evaluation_service,
)

logger = setup_logger(__name__)
generated_results_router = APIRouter()


@generated_results_router.post("/evaluator", response_model=ManualEvaluator, status_code=status.HTTP_201_CREATED)
async def insert_new_evaluator(
        manual_evaluator: ManualEvaluator,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        return result_generation_service.insert_new_evaluator(manual_evaluator)
    except ValueError as e:
        logger.error(f"Failed to insert evaluator: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e),
        )


@generated_results_router.get("/evaluator", response_model=List[ManualEvaluator], status_code=status.HTTP_200_OK)
async def get_evaluators(
        name: Optional[str] = Query(default=None, description="List only evaluators that contain the provided string in their name"),
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        return result_generation_service.list_all_evaluators(name)
    except ValueError as e:
        logger.error(f"Fail while retrieving evaluators: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        )


@generated_results_router.get("/evaluator/{evaluator_entry_id}", response_model=ManualEvaluator, status_code=status.HTTP_200_OK)
async def get_evaluator_by_id(
        evaluator_entry_id: str,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        return result_generation_service.find_evaluator(evaluator_entry_id)
    except ValueError as e:
        logger.error(f"Failed to find evaluator: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        )


@generated_results_router.put("/evaluator/{evaluator_entry_id}", response_model=ManualEvaluator, status_code=status.HTTP_200_OK)
async def update_evaluator(
        evaluator_entry_id: str,
        updated_evaluator: ManualEvaluator,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        result_generation_service.find_evaluator(evaluator_entry_id)
    except ValueError as e:
        logger.error(f"Failed to find evaluator: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        )
    
    try:
        return result_generation_service.update_evaluator(evaluator_entry_id, updated_evaluator)
    except ValueError as e:
        logger.error(f"Failed to update evaluator: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        )


@generated_results_router.delete("/evaluator/{evaluator_entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluator_with_evaluations(
        evaluator_entry_id: str,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        result_generation_service.find_evaluator(evaluator_entry_id)
    except ValueError as e:
        logger.error(f"Failed to find evaluator: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        )
    
    try:
        return result_generation_service.delete_evaluator(evaluator_entry_id)
    except ValueError as e:
        logger.error(f"Failed to update evaluator: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        )


@generated_results_router.post("/generate", response_model=GenerationResult, status_code=status.HTTP_201_CREATED)
async def generate_new_stored_result(
        generation_result_run: GenerationResultRun, question_entry_id: str,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
        workflow_service: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    try:
        workflow_service.get_workflow_entry_by_id(generation_result_run.workflow_system_id)
    except ValueError as e:
        logger.warning(f"Workflow not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retrieve reference: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return result_generation_service.generate_stored_result(
            run=generation_result_run, question_entry_id=question_entry_id,
        )
    except ValueError as e:
        logger.warning(f"Component for result generation not found: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retrieve reference: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.put("/generate/{generation_result_entry_id}", response_model=GenerationResult, status_code=status.HTTP_201_CREATED)
async def renew_stored_result(
        generation_result_entry_id: str,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
        workflow_service: WorkflowSystemStorageService = Depends(get_workflow_storage),
):
    try:
        existing_run = result_generation_service.get_generation_result_entry(gen_result_entry_id=generation_result_entry_id)
    except ValueError as e:
        logger.warning(f"Error finding generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    try:
        workflow_service.get_workflow_entry_by_id(existing_run.generation_run.workflow_system_id)
    except ValueError as e:
        logger.warning(f"Workflow not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retrieve reference: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return result_generation_service.regenerate_stored_result(generation_result_entry_id=generation_result_entry_id)
    except ValueError as e:
        logger.warning(f"Component for result generation not found: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retrieve reference: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.get(
    "/result_generation_runs", response_model=List[GenerationResultRun], status_code=status.HTTP_200_OK,
)
async def get_existing_result_generation_runs(
        run_name: Optional[str] = Query(default=None),
        workflow_system_id: Optional[str] = Query(default=None),
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        return result_generation_service.find_generation_runs(
            run_name=run_name, workflow_id=workflow_system_id,
        )
    except ValueError as e:
        logger.warning(f"Error finding described generation run: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation run: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.delete(
    "/result_generation_runs", status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_whole_result_generation_run(
        generation_result_run: GenerationResultRun,
        delete_with_associated_chat: bool = Query(False, description="Whether to delete the chat as well"),
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        gen_result_entries = result_generation_service.list_generation_results(
            run_name=generation_result_run.name, workflow_id=generation_result_run.workflow_system_id,
        )
        for generation_result_entry in gen_result_entries:
            generation_result_entry_id = generation_result_entry.id
            result_generation_service.delete_generation_result_entry(
                gen_result_entry_id=generation_result_entry_id, delete_with_associated_chat=delete_with_associated_chat,
            )
    except ValueError as e:
        logger.warning(f"Error deleting generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during deletion for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.get("/", response_model=List[GenerationResult], status_code=status.HTTP_200_OK)
async def list_all_stored_generated_results(
        run_name: Optional[str] = Query(default=None),
        run_name_regex: Optional[str] = Query(default=None),
        workflow_system_id: Optional[str] = Query(default=None),
        question_id: Optional[str] = Query(default=None),
        chat_id: Optional[str] = Query(default=None),
        manual_eval_required: Optional[bool] = Query(default=None),
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        return result_generation_service.list_generation_results(
            run_name=run_name, run_name_regex=run_name_regex, workflow_id=workflow_system_id, question_id=question_id, chat_id=chat_id,
            manual_eval_required=manual_eval_required,
        )
    except ValueError as e:
        logger.warning(f"Error finding described generation results: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation results: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.put(
    "/{generation_result_entry_id}/automatic_evaluation/", response_model=GenerationResult,
    status_code=status.HTTP_200_OK,
)
async def perform_automatic_evaluation_for_stored_generated_result(
        generation_result_entry_id: str,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
        automatic_evaluation_service: AutomaticEvaluationService = Depends(get_automatic_evaluation_service),
):
    try:
        gen_res = result_generation_service.get_generation_result_entry(gen_result_entry_id=generation_result_entry_id)
    except ValueError as e:
        logger.warning(f"Error finding generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gen_res = automatic_evaluation_service.extract_response_latency(gen_res)
        gen_res = await automatic_evaluation_service.run_accuracy_analysis(gen_res)
        gen_res = automatic_evaluation_service.run_retrieval_performance_analysis(gen_res)
        return gen_res
    except ValueError as e:
        logger.warning(f"Error augmenting generation result with automatic evaluation metrics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error augmenting generation result with automatic evaluation metrics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.put(
    "/{generation_result_entry_id}/automatic_evaluation/retrieval", response_model=GenerationResult,
    status_code=status.HTTP_200_OK,
)
async def perform_automatic_retrieval_evaluation_for_stored_generated_result(
        generation_result_entry_id: str,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
        automatic_evaluation_service: AutomaticEvaluationService = Depends(get_automatic_evaluation_service),
):
    try:
        gen_res = result_generation_service.get_generation_result_entry(gen_result_entry_id=generation_result_entry_id)
    except ValueError as e:
        logger.warning(f"Error finding generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gen_res = automatic_evaluation_service.run_retrieval_performance_analysis(gen_res)
        return gen_res
    except ValueError as e:
        logger.warning(f"Error augmenting generation result with automatic evaluation metrics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error augmenting generation result with automatic evaluation metrics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.put(
    "/{generation_result_entry_id}/correctness_evaluation/", response_model=GenerationResult,
    status_code=status.HTTP_200_OK,
)
async def insert_correctness_evaluation_for_stored_generated_result(
        generation_result_entry_id: str,
        evaluator: str = Query(description="Valid MongoDB entry ID of the evaluator who created with evaluation"),
        likert_correctness_score: conint(ge=1, le=5) = Query(..., description="Score must be 1–5"),
        counter_factual_conflicts: Optional[int] = Query(default=None),
        counter_input_conflicts: Optional[int] = Query(default=None),
        counter_context_conflicts: Optional[int] = Query(default=None),
        note: Optional[str] = Query(default=None),
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
        manual_evaluation_service: ManualEvaluationService = Depends(get_manual_evaluation_service),
):
    try:
        evaluator_id = result_generation_service.find_evaluator(evaluator).id
    except ValueError as e:
        logger.warning(f"Error finding evaluator for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gen_res = result_generation_service.get_generation_result_entry(gen_result_entry_id=generation_result_entry_id)
    except ValueError as e:
        logger.warning(f"Error finding generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gen_res = manual_evaluation_service.write_correctness_evaluation(
            generation_result=gen_res, evaluator_id=evaluator_id, likert_correctness_score=likert_correctness_score,
            counter_factual_conflicts=counter_factual_conflicts, counter_input_conflicts=counter_input_conflicts,
            counter_context_conflicts=counter_context_conflicts, note=note,
        )
        return gen_res
    except ValueError as e:
        logger.warning(f"Error augmenting generation result with provided correctness measures: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error augmenting generation result with provided correctness measures: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.put(
    "/{generation_result_entry_id}/factuality_evaluation/", response_model=GenerationResult,
    status_code=status.HTTP_200_OK,
)
async def insert_factuality_evaluation_for_stored_generated_result(
        generation_result_entry_id: str,
        evaluator: str = Query(description="Valid MongoDB entry ID of the evaluator who created with evaluation"),
        counter_facts_overall: int = Query(description="The facts counted in the answer"),
        counter_facts_backed: int = Query(descruption="The facts counted in the answer THAT ARE also backed by the retrieval results"),
        note: Optional[str] = Query(default=None),
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
        manual_evaluation_service: ManualEvaluationService = Depends(get_manual_evaluation_service),
):
    try:
        evaluator_id = result_generation_service.find_evaluator(evaluator).id
    except ValueError as e:
        logger.warning(f"Error finding evaluator for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gen_res = result_generation_service.get_generation_result_entry(gen_result_entry_id=generation_result_entry_id)
    except ValueError as e:
        logger.warning(f"Error finding generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gen_res = manual_evaluation_service.write_factuality_evaluation(
            generation_result=gen_res, evaluator_id=evaluator_id, counter_facts_overall=counter_facts_overall,
            counter_facts_backed=counter_facts_backed, note=note,
        )
        return gen_res
    except ValueError as e:
        logger.warning(f"Error augmenting generation result with provided factuality measures: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error augmenting generation result with provided factuality measures: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.put(
    "/{generation_result_entry_id}/requires_manual_evaluation/", response_model=GenerationResult,
    status_code=status.HTTP_200_OK,
)
async def update_manual_evaluation_bool(
        generation_result_entry_id: str,
        requires_manual_evaluation: bool = Query(description="Set whether this generation result needs manual update"),
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        gen_res = result_generation_service.get_generation_result_entry(gen_result_entry_id=generation_result_entry_id)
    except ValueError as e:
        logger.warning(f"Error finding generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gen_res = result_generation_service.update_generation_result_entry(
            gen_result_entry_id=gen_res.id,
            update_data={
                "requires_manual_evaluation": requires_manual_evaluation,
            },
        )
        return gen_res
    except ValueError as e:
        logger.warning(f"Error setting 'requires_manual_evaluation' in generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting 'requires_manual_evaluation' in generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.get(
    "/{generation_result_entry_id}", response_model=GenerationResult, status_code=status.HTTP_200_OK,
)
async def get_generated_result(
        generation_result_entry_id: str,
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        return result_generation_service.get_generation_result_entry(gen_result_entry_id=generation_result_entry_id)
    except ValueError as e:
        logger.warning(f"Error finding generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during search for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@generated_results_router.delete(
    "/{generation_result_entry_id}", status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_generated_result(
        generation_result_entry_id: str,
        delete_with_associated_chat: bool = Query(False, description="Whether to delete the chat as well"),
        result_generation_service: ResultGenerationService = Depends(get_result_generation_service),
):
    try:
        result_generation_service.delete_generation_result_entry(
            gen_result_entry_id=generation_result_entry_id, delete_with_associated_chat=delete_with_associated_chat,
        )
    except ValueError as e:
        logger.warning(f"Error deleting generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failure during deletion for generation result: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
