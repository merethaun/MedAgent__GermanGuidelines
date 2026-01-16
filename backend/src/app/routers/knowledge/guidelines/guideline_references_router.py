from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response

from app.exceptions.knowledge.guidelines import GuidelineNotFoundError
from app.models.knowledge.guidelines import (
    GuidelineReference, ReferenceType, GuidelineReferenceGroup, GuidelineTextReference,
)
from app.models.knowledge.guidelines.keyword_models import KeywordsForReferenceRequest, KeywordLLMSettings, YAKESettings
from app.services.knowledge.guidelines import GuidelineService, AWMFDocumentsService
from app.services.knowledge.guidelines.keywords.keyword_service import KeywordService
from app.services.knowledge.guidelines.references import GuidelineReferenceService
from app.services.knowledge.guidelines.references.reference_finder_service import ReferenceFinderService
from app.utils.logger import setup_logger
from app.utils.service_creators import (
    get_guideline_reference_service, get_guideline_service, get_awmf_documents_service, get_reference_finder_service, get_keyword_service,
)

logger = setup_logger(__name__)
references_router = APIRouter()


@references_router.post("/group", response_model=GuidelineReferenceGroup, status_code=status.HTTP_201_CREATED)
async def insert_guideline_reference_group(
        reference_group: GuidelineReferenceGroup,
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReferenceGroup:
    logger.debug(f"Received request to create reference group: {reference_group.name}")
    try:
        reference_service.get_reference_group_by_id(reference_group.id) if reference_group.id else None
        logger.error(
            f"Guideline reference group with ID {reference_group.id} already exists (will not be created / overwritten)",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Guideline reference group with this id already exists",
        )
    except Exception:
        pass
    
    try:
        reference_service.get_reference_group_by_name(reference_group.name) if reference_group.name else None
        logger.error(
            f"Guideline reference group with name {reference_group.name} already exists (will not be created / overwritten)",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Guideline reference group with this name already exists",
        )
    except Exception:
        pass
    
    try:
        created_reference_group = reference_service.create_reference_group(reference_group)
        logger.info(f"Successfully created reference group with ID: {created_reference_group.id}")
        return created_reference_group
    except Exception as e:
        logger.error(f"Failed to create reference group: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create reference group: {str(e)}",
        )


@references_router.get("/group", response_model=List[GuidelineReferenceGroup], status_code=status.HTTP_200_OK)
async def get_reference_groups(
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> List[GuidelineReferenceGroup]:
    logger.debug("Received request to get all reference groups")
    try:
        responses = reference_service.get_all_reference_groups()
        logger.info(f"Successfully retrieved reference groups")
        logger.debug(f"Reference groups: {responses}")
        return responses
    except Exception as e:
        logger.error(f"Error retrieving reference groups: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving reference groups: {str(e)}",
        )


@references_router.get(
    "/group/{reference_group_id}", response_model=GuidelineReferenceGroup, status_code=status.HTTP_200_OK,
)
async def get_reference_group_by_id(
        reference_group_id: str,
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReferenceGroup:
    logger.debug(f"Received request to get reference group with ID: {reference_group_id}")
    try:
        response = reference_service.get_reference_group_by_id(reference_group_id)
        logger.info(f"Successfully retrieved reference group with ID: {reference_group_id}")
        return response
    except Exception as e:
        logger.error(f"Error retrieving reference group with ID {reference_group_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving reference group: {str(e)}",
        )


@references_router.delete("/group/{reference_group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference_group(
        reference_group_id: str,
        delete_references: bool = Query(
            False,
            description="Whether to delete any associated references. If false, will fail if guideline has references.",
        ),
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
):
    logger.debug(f"Received request to delete reference group with ID: {reference_group_id}")
    try:
        reference_service.get_reference_group_by_id(reference_group_id)
    except Exception as e:
        logger.warning(f"Reference group with ID {reference_group_id} not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    
    if delete_references:
        try:
            reference_service.delete_references_by_reference_group_id(reference_group_id)
            logger.info(f"Successfully deleted all references in reference group with ID: {reference_group_id}")
        except Exception as e:
            logger.warning(f"Failed to delete references in reference group with ID {reference_group_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete references in reference group: {str(e)}",
            )
    else:
        if reference_service.get_all_references(reference_group_id=reference_group_id):
            logger.warning(
                f"Reference group with ID {reference_group_id} has associated references. Set delete_references=True to delete references.",
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reference group with this id has associated references. Set delete_references=True to delete references.",
            )
    
    try:
        reference_service.delete_reference_group_by_id(reference_group_id)
        logger.info(f"Successfully deleted reference group with ID: {reference_group_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        logger.warning(f"Reference group with ID {reference_group_id} not found: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
        )


@references_router.put(
    "/group/{reference_group_id}", response_model=GuidelineReferenceGroup, status_code=status.HTTP_200_OK,
)
async def update_reference_group(
        reference_group_id: str,
        update_data: GuidelineReferenceGroup,
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReferenceGroup:
    """
    Update an existing guideline reference group by its ID.
    Args:
        reference_group_id: ID of the reference group to update.
        update_data: The updated details of the reference group.
        reference_service: Service for handling guideline reference groups.
    Returns:
        Updated guideline reference group object.
    """
    logger.debug(f"Received request to update reference group with ID: {reference_group_id}")
    try:
        existing_group = reference_service.get_reference_group_by_id(reference_group_id)
        if not existing_group:
            logger.warning(f"Reference group with ID {reference_group_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference group not found")
        
        updated_group = reference_service.update_reference_group(reference_group_id, update_data)
        logger.info(f"Successfully updated reference group with ID: {reference_group_id}")
        return updated_group
    
    except Exception as e:
        logger.error(f"Error updating reference group with ID {reference_group_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating reference group: {str(e)}",
        )


@references_router.get("/detect/text", response_model=GuidelineTextReference, status_code=status.HTTP_200_OK)
async def detect_text_reference(
        guideline_id: str = Query(description="Filter references by guideline ID"),
        query: str = Query(description="Text to search for in guideline text"),
        start_page: Optional[int] = Query(default=None, description="Page number to start search from"),
        end_page: Optional[int] = Query(default=None, description="Page number where to end search"),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
        reference_finder_service: ReferenceFinderService = Depends(get_reference_finder_service),
):
    try:
        guideline = guideline_service.get_guideline_by_id(guideline_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    try:
        documents_service.get_guideline_pdf(guideline)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"Guideline document (PDF) required for interaction NOT found: {str(e)}",
        )
    
    try:
        return reference_finder_service.find_text_reference(
            guideline, query, start_page=start_page or 0, end_page=end_page or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error in text reference query: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in text reference query: {str(e)}",
        )


@references_router.get("/find/text", status_code=status.HTTP_200_OK)
async def find_text_on_page(
        guideline_id: str = Query(description="Filter references by guideline ID"),
        page: Optional[int] = Query(default=None, description="Page number from which to retrieve text from"),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
        reference_finder_service: ReferenceFinderService = Depends(get_reference_finder_service),
):
    try:
        guideline = guideline_service.get_guideline_by_id(guideline_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    try:
        documents_service.get_guideline_pdf(guideline)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"Guideline document (PDF) required for interaction NOT found: {str(e)}",
        )
    
    try:
        return reference_finder_service.get_text(guideline, page)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in text reference query: {str(e)}",
        )


# TODO: add "extract table markdown" given position on page

@references_router.post("/", response_model=GuidelineReference, status_code=status.HTTP_201_CREATED)
async def insert_guideline_reference(
        reference: GuidelineReference,
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
        guideline_service: GuidelineService = Depends(get_guideline_service),
) -> GuidelineReference:
    """
    Insert a new guideline reference into the database.
    """
    logger.debug(f"Received request to create reference of type: {reference.type}")
    try:
        guideline_service.get_guideline_by_id(reference.guideline_id)
    except GuidelineNotFoundError as e:
        logger.warning(f"Guideline with ID {reference.guideline_id} not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    try:
        reference_service.get_reference_group_by_id(reference.reference_group_id)
    except Exception as e:
        logger.warning(f"Reference group with ID {reference.reference_group_id} not found: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    try:
        created_reference = reference_service.create_reference(reference)
        logger.info(f"Successfully created reference with ID: {created_reference.id}")
        return created_reference
    except Exception as e:
        logger.error(f"Failed to create reference: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create reference: {str(e)}",
        )


@references_router.get("/", response_model=List[GuidelineReference])
async def get_references(
        guideline_id: Optional[str] = Query(None, description="Filter references by guideline ID"),
        guideline_reference_group: Optional[str] = Query(None, description="Filter references by reference group ID"),
        reference_type: Optional[ReferenceType] = Query(None, description="Filter references by reference type"),
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> List[GuidelineReference]:
    """
    Get guideline references with optional filtering by guideline ID and reference type.
    """
    try:
        return reference_service.get_all_references(
            guideline_id=guideline_id, reference_group_id=guideline_reference_group, reference_type=reference_type,
        )
    except ValueError as e:
        if "Invalid guideline_id format" in str(e):
            logger.warning(f"Invalid guideline_id: {guideline_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        logger.error(f"Error in reference query parameters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error retrieving references: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving references: {str(e)}",
        )


@references_router.get("/{reference_id}", response_model=GuidelineReference)
async def get_reference_by_id(
        reference_id: str,
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReference:
    """
    Get a guideline reference by its ID.

    Args:
        reference_id: The ID of the reference to retrieve.
        reference_service: Service for handling guideline references.

    Returns:
        The guideline reference object if found.
    """
    logger.debug(f"Received request to get reference with ID: {reference_id}")
    try:
        reference = reference_service.get_reference_by_id(reference_id)
        logger.info(f"Successfully retrieved reference with ID: {reference_id}")
        return reference
    except ValueError as e:
        logger.warning(f"Reference with ID {reference_id} not found: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference with ID {reference_id} not found",
        )
    except Exception as e:
        logger.error(f"Error retrieving reference with ID {reference_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving reference: {str(e)}",
        )


@references_router.delete("/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference(
        reference_id: str,
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
):
    """
    Delete a guideline reference by its ID.

    Args:
        reference_id: The ID of the reference to delete.
        reference_service: Service for handling guideline references.

    Returns:
        204 No Content on successful deletion
    """
    logger.debug(f"Received request to delete reference with ID: {reference_id}")
    try:
        reference_service.delete_reference_by_id(reference_id)
        logger.info(f"Successfully deleted reference with ID: {reference_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        logger.warning(f"Reference with ID {reference_id} not found: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference with ID {reference_id} not found",
        )
    except Exception as e:
        logger.error(f"Error deleting reference with ID {reference_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting reference: {str(e)}",
        )


@references_router.put("/{reference_id}", response_model=GuidelineReference, status_code=status.HTTP_200_OK)
async def update_reference(
        reference_id: str,
        update_data: GuidelineReference,
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
) -> GuidelineReference:
    """
    Update an existing guideline reference by its ID.
    Args:
        reference_id: The ID of the reference to update.
        update_data: The updated details for the reference.
        reference_service: Service for handling guideline references.
    Returns:
        Updated guideline reference object.
    """
    logger.debug(f"Received request to update reference with ID: {reference_id}")
    try:
        existing_reference = reference_service.get_reference_by_id(reference_id)
        if not existing_reference:
            logger.warning(f"Reference with ID {reference_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
        
        updated_reference = reference_service.update_reference(reference_id, update_data)
        logger.info(f"Successfully updated reference with ID: {reference_id}")
        return updated_reference
    
    except Exception as e:
        logger.error(f"Error updating reference with ID {reference_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating reference: {str(e)}",
        )


@references_router.put("/{reference_id}/keywords", response_model=GuidelineReference, status_code=status.HTTP_200_OK)
async def add_keywords_to_reference(
        reference_id: str,
        keyword_adding_settings: KeywordsForReferenceRequest,
        reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
        keywords_service: KeywordService = Depends(get_keyword_service),
) -> GuidelineReference:
    """
    Add keywords (with synonyms) to an existing guideline reference by its ID.
    Returns:
        Updated guideline reference object.
    """
    try:
        existing_reference = reference_service.get_reference_by_id(reference_id)
        if not existing_reference:
            logger.warning(f"Reference with ID {reference_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
        
        text = existing_reference.extract_content()
        
        if keyword_adding_settings.keyword_method == "yake":
            if keyword_adding_settings.yake is None:
                raise HTTPException(status_code=400, detail="yake settings are required when method='yake'.")
            
            yake: YAKESettings = keyword_adding_settings.yake
            try:
                keywords = keywords_service.extract_yake(
                    text, min_keywords=yake.min_keywords, max_keywords=yake.max_keywords, ignore_terms=yake.ignore_terms,
                    language=yake.language, max_n_gram_size=yake.max_n_gram_size,
                    deduplication_threshold=yake.deduplication_threshold,
                )
            except Exception as e:
                logger.error(f"YAKE extraction failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"YAKE extraction failed: {e}")
        
        elif keyword_adding_settings.keyword_method == "llm":
            # LLM path
            if keyword_adding_settings.llm_keywords is None:
                raise HTTPException(status_code=400, detail="llm settings are required when method='llm'.")
            
            llm: KeywordLLMSettings = keyword_adding_settings.llm_keywords
            try:
                keywords = keywords_service.extract_llm(
                    text=text, model=llm.model, api_key=llm.api_key, api_base=llm.api_base, temperature=llm.temperature, max_tokens=llm.max_tokens,
                    scope_description=llm.scope_description, guidance_additions=llm.guidance_additions, ignore_terms=llm.ignore_terms,
                    important_terms=llm.important_terms, examples=llm.examples, min_keywords=llm.min_keywords, max_keywords=llm.max_keywords,
                )
            except Exception as e:
                logger.error(f"LLM extraction failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"LLM extraction failed: {e}")
        else:
            raise HTTPException(status_code=400, detail=f"Invalid keyword method ({keyword_adding_settings.keyword_method}).")
        
        if keyword_adding_settings.apply_synonym_expansion:
            if not keywords:
                logger.warning("No keywords found.")
                return existing_reference
            
            if keyword_adding_settings.synonym_expansion_llm is None:
                raise HTTPException(status_code=400, detail="LLM settings for synoym expansion settings ('llm') are required.")
            try:
                keywords = [
                    synonym.text_with_synonym_replacement
                    for synonym in keywords_service.expand_synonym_for_multiple_terms(
                        llm_config=keyword_adding_settings.synonym_expansion_llm,
                        texts=keywords,
                        min_llm_preference=keyword_adding_settings.min_synonym_llm_confidence,
                        try_english_search=keyword_adding_settings.allow_english_search,
                    )
                ]
            except Exception as e:
                logger.error(f"LLM expansion failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"LLM expansion failed: {e}")
        
        logger.info(f"Keywords added to reference with ID: {reference_id} ({len(keywords)} keywords)")
        
        updated_reference = reference_service.update_reference(reference_id, {"associated_keywords": keywords})
        logger.info(f"Successfully updated reference with ID: {reference_id}")
        return updated_reference
    
    except Exception as e:
        logger.error(f"Error updating reference with ID {reference_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating reference: {str(e)}",
        )
