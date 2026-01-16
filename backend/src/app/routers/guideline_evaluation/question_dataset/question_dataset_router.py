import io
from typing import List, Optional, Dict

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, UploadFile, File, Body
from starlette.responses import StreamingResponse

from app.models.guideline_evaluation.question_dataset.question_entry import QuestionEntry, QuestionGroup
from app.models.guideline_evaluation.question_dataset.question_parser_result import ParseResultResponse
from app.services.guideline_evaluation.question_dataset import QuestionDatasetService, QuestionDatasetParserService
from app.services.knowledge.guidelines.references import GuidelineReferenceService
from app.utils.logger import setup_logger
from app.utils.service_creators import get_question_dataset_parser_service, get_question_dataset_service, get_guideline_reference_service

logger = setup_logger(__name__)
dataset_router = APIRouter()


@dataset_router.post("/group", response_model=QuestionGroup, status_code=status.HTTP_201_CREATED)
async def insert_new_question_group(
        question_group: QuestionGroup,
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
):
    try:
        return dataset_service.insert_new_question_group(question_group)
    except ValueError as e:
        logger.error(f"Failed to insert question group: {str(e)}", exc_info=e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@dataset_router.get("/group", response_model=List[QuestionGroup], status_code=status.HTTP_200_OK)
async def get_question_groups(
        group_name: Optional[str] = Query(default=None, description="List only question groups that contain the provided string in their name"),
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
):
    try:
        return dataset_service.list_all_question_groups(group_name)
    except ValueError as e:
        logger.error(f"Fail while retrieving question groups: {str(e)}", exc_info=e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@dataset_router.get("/group/{question_group_entry_id}", response_model=QuestionGroup, status_code=status.HTTP_200_OK)
async def get_question_group_by_id(
        question_group_entry_id: str,
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
):
    try:
        return dataset_service.find_question_group(question_group_entry_id)
    except ValueError as e:
        logger.error(f"Failed to find question group: {str(e)}", exc_info=e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@dataset_router.put("/group/{question_group_entry_id}", response_model=QuestionGroup, status_code=status.HTTP_200_OK)
async def update_question_group(
        question_group_entry_id: str,
        updated_question_group: QuestionGroup,
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
):
    try:
        dataset_service.find_question_group(question_group_entry_id)
    except ValueError as e:
        logger.error(f"Failed to find question group: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        )
    
    try:
        return dataset_service.update_question_group(question_group_entry_id, updated_question_group)
    except ValueError as e:
        logger.error(f"Failed to update question group: {str(e)}", exc_info=e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@dataset_router.delete("/group/{question_group_entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question_group_with_questions(
        question_group_entry_id: str,
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
):
    try:
        dataset_service.find_question_group(question_group_entry_id)
    except ValueError as e:
        logger.error(f"Failed to find question_group: {str(e)}", exc_info=e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    
    try:
        return dataset_service.delete_question_group(question_group_entry_id)
    except ValueError as e:
        logger.error(f"Failed to update evaluator: {str(e)}", exc_info=e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@dataset_router.post("/parse", response_model=ParseResultResponse, status_code=status.HTTP_201_CREATED)
async def parse_question_dataset(
        csv_file: UploadFile = File(...),
        dataset_parser_service: QuestionDatasetParserService = Depends(get_question_dataset_parser_service),
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
):
    try:
        df = pd.read_csv(csv_file.file, encoding="utf-8", encoding_errors="ignore")
    except Exception as e:
        logger.error(f"Failed to read CSV file: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    finally:
        await csv_file.close()
    
    failed_entries = []
    
    parsed_entries, failed_from_parsing = dataset_parser_service.csv_to_parser_result(df)
    failed_entries.extend(failed_from_parsing)
    
    inserted_ids, failed_from_insertion = dataset_parser_service.insert_question_entries_from_parser_result(
        parsed_entries,
    )
    for fail in failed_from_insertion:
        failed_entries.extend(dataset_parser_service.find_csv_entries_based_on_parser_result(df, fail))
    
    inserted_entries = [
        dataset_service.get_question_entry_by_id(question_id) for question_id in inserted_ids
    ]
    
    failed_entries_dict = [
        entry if isinstance(entry, dict)
        else entry.to_dict() if isinstance(entry, pd.Series)
        else entry.dict()
        for entry in failed_entries
    ]
    
    return ParseResultResponse(
        inserted_entries=inserted_entries,
        failed_entries=failed_entries_dict,
    )


@dataset_router.post("/parse/failed-csv", response_class=StreamingResponse)
async def download_failed_csv(
        failed_entries: List[Dict] = Body(
            ..., examples=[
                [
                    {
                        "Question supercategory": "Simple",
                        "Question subcategory": "Text",
                        "Question": "Welche Bildgebende Diagnostik ...?",
                        "Answer ID": 7.1,
                        "Answer Guideline": "007-006",
                        "Answer Gpage": 17,
                        "Answer": "Ultraschalluntersuchung ...",
                        "Comment": "Diagnostik",
                    },
                ],
            ],
        ),
):
    if not failed_entries:
        raise HTTPException(status_code=400, detail="No failed entries provided.")
    
    # Convert to CSV in memory
    csv_stream = io.StringIO()
    pd.DataFrame(failed_entries).to_csv(csv_stream, index=False)
    csv_stream.seek(0)
    
    return StreamingResponse(
        csv_stream,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=failed_entries.csv"},
    )


@dataset_router.post("/", response_model=QuestionEntry, status_code=status.HTTP_201_CREATED)
async def create_question_entry(
        question_entry: QuestionEntry,
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> QuestionEntry:
    """
    Create a new question entry in the dataset.
    """
    try:
        for ref in question_entry.expected_retrieval:
            reference_service.get_reference_by_id(ref)
    except ValueError as e:
        logger.warning(f"Reference not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retrieve reference: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return dataset_service.create_dataset_entry(question_entry)
    except ValueError as e:
        logger.warning(f"Validation failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create question entry: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@dataset_router.get("/{entry_id}", response_model=QuestionEntry)
async def get_question_entry_by_id(
        entry_id: str,
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
) -> QuestionEntry:
    """
    Retrieve a single question entry by ID.
    """
    try:
        return dataset_service.get_question_entry_by_id(entry_id)
    except ValueError as e:
        logger.warning(f"Question entry not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retrieve question entry: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@dataset_router.get("/", response_model=List[QuestionEntry])
async def get_question_entries(
        question: Optional[str] = Query(None, description="Partial match on the question text"),
        super_class: Optional[str] = Query(None, description="Super question class"),
        sub_class: Optional[str] = Query(None, description="Sub question class (requires super_class)"),
        question_group_id: Optional[str] = Query(
            None, description="Matching question group",
        ),
        reference_id: Optional[str] = Query(
            None, description="At least one reference of question entry must be this reference",
        ),
        guideline_id: Optional[str] = Query(
            None,
            description="At least one reference of question entry must be pointing to this guideline "
                        "<ul><li><small>In combination with reference_id: reference must match this guideline</small></li>"
                        "<li><small>In combination with group: some reference must match guideline AND reference group</small></li></ul>",
        ),
        reference_group_id: Optional[str] = Query(
            None,
            description="At least one reference of question entry must be pointing to this reference group"
                        "<ul><li><small>In combination with reference_id: reference must match this reference group</small></li>"
                        "<li><small>In combination with guideline: some reference must match guideline AND reference group</small></li></ul>",
        ),
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
) -> List[QuestionEntry]:
    """
    Get a list of question entries filtered by optional parameters.
    """
    try:
        return dataset_service.get_question_entries(
            question=question,
            super_class=super_class,
            sub_class=sub_class,
            guideline_id=guideline_id,
            reference_group_id=reference_group_id,
            reference_id=reference_id,
            question_group_id=question_group_id,
        )
    except ValueError as e:
        logger.warning(f"Invalid input parameters: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retrieve question entries: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@dataset_router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question_entry(
        entry_id: str,
        delete_references: bool = Query(default=True, description="Whether to delete any associated references."),
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
):
    """
    Delete a question entry by ID.
    """
    if delete_references:
        try:
            references = dataset_service.get_question_entry_by_id(entry_id).expected_retrieval
            
            deleted, non_existing = [], []
            for ref in references:
                try:
                    reference_service.delete_reference_by_id(ref)
                    deleted.append(ref)
                    logger.debug(f"Deleted reference with ID: {ref}")
                except ValueError as e:
                    non_existing.append(ref)
                    logger.debug(f"Reference with ID {ref} not found, assumed to be not existing (error: {e})")
            logger.info(f"Successfully deleted {len(deleted)} references")
            if len(non_existing) > 0:
                logger.warning(
                    f"The following references were not found, therefor are assumed to not exist anymore: {non_existing}",
                )
        
        except ValueError as e:
            logger.warning(f"Not found: {str(e)}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to delete references: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        dataset_service.delete_question_entry(entry_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        logger.warning(f"Question entry not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete question entry: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@dataset_router.put("/{entry_id}", response_model=QuestionEntry)
async def update_question_entry(
        entry_id: str,
        update_data: QuestionEntry,
        dataset_service: QuestionDatasetService = Depends(get_question_dataset_service),
) -> QuestionEntry:
    """
    Update an existing question entry.
    """
    try:
        return dataset_service.update_question_entry(entry_id, update_data)
    except ValueError as e:
        logger.warning(f"Update failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update question entry: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
