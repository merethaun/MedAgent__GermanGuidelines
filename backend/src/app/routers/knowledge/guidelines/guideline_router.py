from datetime import datetime, timezone
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, status, Query, Depends, UploadFile, File
from starlette.responses import FileResponse

from app.constants.awmf_website_constants import DEFAULT_URL_AWMF_GUIDELINE_SEARCH
from app.exceptions.knowledge.guidelines import GuidelineNotFoundError, WebsiteNotAsExpectedError
from app.models.knowledge.guidelines import (
    GuidelineEntry, GuidelineValidationResult, AWMFSearchResult, AWMFExtractedGuidelineMetadata,
)
from app.services.knowledge.guidelines import (
    GuidelineService, AWMFDocumentsService, GuidelineValidationService, AWMFWebsiteInteractionService,
)
from app.services.knowledge.guidelines.references import GuidelineReferenceService
from app.utils.service_creators import (
    get_guideline_service, get_guideline_validation_service, get_awmf_website_interaction_service, get_awmf_documents_service,
    get_guideline_reference_service,
)

guideline_router = APIRouter()


@guideline_router.post("/", response_model=str, status_code=status.HTTP_201_CREATED)
def create_guideline(
        guideline: GuidelineEntry, service: GuidelineService = Depends(get_guideline_service),
):
    """
    Create a new guideline.
    """
    inserted_guideline = service.create_guideline(guideline)
    return str(inserted_guideline.id)


@guideline_router.get("/", response_model=List[GuidelineEntry])
def get_all_guidelines(
        valid: Optional[bool] = Query(
            None,
            description="Filter by guideline validity (True/False) -> relates to validity set in guideline entry, not whether the entry is valid",
        ),
        extended_validity: Optional[bool] = Query(
            None, description="Filter by whether validity was officially extended",
        ),
        is_living_guideline: Optional[bool] = Query(None, description="Filter living guidelines (validity_range=1)"),
        leading_organizations: Optional[List[str]] = Query(
            None,
            description="Presented organizations are leading / main publisher for the guidelines (partial match with name of organization)",
            examples=[["DGMKG"]],
        ),
        organizations: Optional[List[str]] = Query(
            None, description="Partial match for publishing organizations", examples=[["DGMKG", "AGOKi"]],
        ),
        keyword_all: Optional[List[str]] = Query(
            None, description="Match guidelines that contain all provided keywords",
        ),
        keyword_any: Optional[List[str]] = Query(
            None, description="Match guidelines that contain any of the provided keywords",
        ),
        awmf_register_number: Optional[str] = Query(
            None,
            description="Look for a match of the 'compressed' version of the AWMF register number (ddd-ddd format) -> Will be automatically extracted from whatever string is provided",
        ),
        awmf_register_number_full: Optional[str] = Query(
            None, description="Full AWMF register number (e.g., 007-106L)",
        ),
        awmf_class: Optional[str] = Query(None, description="Guideline classification (e.g., S1, S2k, S3)"),
        publication_range_start: Optional[datetime] = Query(None, description="Start of publication date range"),
        publication_range_end: Optional[datetime] = Query(None, description="End of publication date range"),
        download_range_start: Optional[datetime] = Query(None, description="Start of download date range"),
        download_range_end: Optional[datetime] = Query(None, description="End of download date range"),
        missing_pdf: Optional[bool] = Query(
            None,
            description="Filter guidelines without PDF (True) or only with assigned PDFs (False). Defaults to None, which means no filter is applied.",
        ),
        service: GuidelineService = Depends(get_guideline_service),
):
    """
    Fetch all guidelines, optionally filtered by multiple parameters.
    - Filters can be combined freely.
    """
    return service.get_all_guidelines(
        valid=valid, extended_validity=extended_validity, is_living_guideline=is_living_guideline,
        leading_organizations=leading_organizations, organizations=organizations, keyword_all=keyword_all,
        keyword_any=keyword_any, awmf_register_number=awmf_register_number,
        awmf_register_number_full=awmf_register_number_full, awmf_class=awmf_class,
        publication_range_start=publication_range_start, publication_range_end=publication_range_end,
        download_range_start=download_range_start, download_range_end=download_range_end,
        missing_pdf=missing_pdf,
    )


@guideline_router.get(
    "/incomplete_guideline_entries", status_code=status.HTTP_200_OK, response_model=Dict[str, GuidelineValidationResult],
)
def get_all_incomplete_guidelines(
        guideline_service: GuidelineService = Depends(get_guideline_service),
        guideline_validation_service: GuidelineValidationService = Depends(get_guideline_validation_service),
):
    """
    Returns a dict of all guideline entries that are valid BUT NOT complete (parts for full definition missing).
    - Key: guideline_id
    - Value: GuidelineValidationResult object (describing why incomplete)
    """
    guidelines = guideline_service.get_all_guidelines()
    
    incomplete_valid_guidelines = {}
    for guideline in guidelines:
        guideline_validation_result = guideline_validation_service.validate_guideline(guideline)
        if guideline_validation_result.is_valid and not guideline_validation_result.is_complete:
            # we can assume that the guideline ids are unique
            incomplete_valid_guidelines[guideline.id] = guideline_validation_result
    return incomplete_valid_guidelines


@guideline_router.get(
    "/invalid_guideline_entries", status_code=status.HTTP_200_OK, response_model=Dict[str, GuidelineValidationResult],
)
def get_all_invalid_guidelines(
        guideline_service: GuidelineService = Depends(get_guideline_service),
        guideline_validation_service: GuidelineValidationService = Depends(get_guideline_validation_service),
):
    """
    Returns a dict of all guideline entries that are not valid.
    - Key: guideline_id
    - Value: GuidelineValidationResult object (describing why incomplete)
    """
    guidelines = guideline_service.get_all_guidelines()
    
    invalid_valid_guidelines = {}
    for guideline in guidelines:
        guideline_validation_result = guideline_validation_service.validate_guideline(guideline)
        if not guideline_validation_result.is_valid:
            # we can assume that the guideline ids are unique
            invalid_valid_guidelines[guideline.id] = guideline_validation_result
    return invalid_valid_guidelines


@guideline_router.get("/unlinked-pdfs", status_code=status.HTTP_200_OK, response_model=List[str])
def list_unlinked_pdfs(
        guideline_service: GuidelineService = Depends(get_guideline_service),
        awmf_documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
):
    """
    List all PDF files in the guideline PDF folder that are not linked to any guideline entry in the MongoDB.
    """
    all_guidelines = guideline_service.get_all_guidelines()
    return awmf_documents_service.get_unlinked_pdf_files(all_guidelines)


@guideline_router.delete("/unlinked-pdfs", status_code=status.HTTP_200_OK)
def delete_unlinked_pdfs(
        guideline_service: GuidelineService = Depends(get_guideline_service),
        awmf_documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
):
    """
    Deletes all PDF files in the guideline PDF folder that are not linked to any guideline entry in the MongoDB.
    """
    all_guidelines = guideline_service.get_all_guidelines()
    number_of_removed_pdfs = awmf_documents_service.remove_unlinked_pdf_files(all_guidelines)
    return {"message": f"Successfully removed {number_of_removed_pdfs} unlinked PDF files."}


@guideline_router.get("/awmf/search", response_model=AWMFSearchResult)
def find_guidelines_in_awmf_search(
        search_url: str = Query(
            default=DEFAULT_URL_AWMF_GUIDELINE_SEARCH,
            description="URL of the AWMF search page to query.",
        ),
        awmf_website_service: AWMFWebsiteInteractionService = Depends(get_awmf_website_interaction_service),
):
    """
    Calls the AWMF website and returns a list of guideline detail page URLs found on the search result page.
    """
    try:
        return awmf_website_service.extract_detail_urls_from_search(search_url)
    except WebsiteNotAsExpectedError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise e


@guideline_router.get("/awmf/details", response_model=AWMFExtractedGuidelineMetadata)
def extract_guideline_metadata_from_awmf_detail_page(
        detail_page_url: str = Query(
            ..., description="URL of the guideline detail page to extract metadata from.",
        ),
        awmf_website_service: AWMFWebsiteInteractionService = Depends(get_awmf_website_interaction_service),
):
    """
    Given a guideline detail page URL, extracts the guideline metadata from the page and return a structured representation.
    """
    try:
        return awmf_website_service.extract_guideline_metadata_from_detail_page(str(detail_page_url))
    except WebsiteNotAsExpectedError as e:
        raise HTTPException(status_code=422, detail={"url": e.url, "reason": e.message})
    except Exception as e:
        raise e


@guideline_router.post("/awmf/details_from_structure", response_model=GuidelineEntry)
def create_guideline_from_awmf_detail_metadata_structure(
        awmf_extracted_guideline_metadata: AWMFExtractedGuidelineMetadata = Query(
            ..., description="The guideline metadata extracted from the guideline detail page.",
        ),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        awmf_website_service: AWMFWebsiteInteractionService = Depends(get_awmf_website_interaction_service),
        awmf_documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
):
    """
    Given the structured, extracted guideline metadata, create a new guideline entry in the database and download the responding PDF file.
    """
    try:
        guideline_entry_object = awmf_website_service.transform_extracted_metadata_to_guideline_entry(
            awmf_extracted_guideline_metadata,
        )
        created_guideline = guideline_service.create_guideline(guideline_entry_object)
        pdf_url = awmf_extracted_guideline_metadata.download_url
        if not pdf_url:
            raise ValueError("No PDF URL provided in extracted metadata.")
        
        created_guideline = awmf_documents_service.download_and_store_guideline_pdf(
            guideline=created_guideline,
            url=str(pdf_url),
            download_date=datetime.now(timezone.utc),
            overwrite_existing=True,
            remove_old_file=True,
        )
        
        created_guideline = guideline_service.update_guideline(created_guideline.id, created_guideline)
        return created_guideline
    
    
    except GuidelineNotFoundError as e:
        if 'created_guideline' in locals():
            try:
                # noinspection PyUnboundLocalVariable
                guideline_service.delete_guideline(created_guideline.id)
                awmf_documents_service.delete_guideline_pdf(created_guideline.download_information.file_path)
            except Exception as cleanup_error:
                raise HTTPException(
                    status_code=500, detail=f"Failed to create guideline and cleanup failed: {cleanup_error}",
                ) from e
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    
    except Exception as e:
        # If any step fails, ensure rollback of the inserted guideline
        if 'created_guideline' in locals():
            try:
                # noinspection PyUnboundLocalVariable
                guideline_service.delete_guideline(created_guideline.id)
            except Exception as cleanup_error:
                raise HTTPException(
                    status_code=500, detail=f"Failed to create guideline and cleanup failed: {cleanup_error}",
                ) from e
        raise HTTPException(status_code=500, detail=f"Failed to create guideline: {str(e)}")


@guideline_router.post("/awmf/details", response_model=GuidelineEntry)
def create_guideline_from_awmf_detail_page(
        detail_page_url: str = Query(
            ..., description="URL of the guideline detail page to extract metadata from.",
        ),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        awmf_website_service: AWMFWebsiteInteractionService = Depends(get_awmf_website_interaction_service),
        awmf_documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
):
    """
    Given the AWMF details page, extract structured, extracted guideline metadata, create a new guideline entry in the database and download the responding PDF file.
    """
    try:
        awmf_extracted_guideline_metadata: AWMFExtractedGuidelineMetadata = awmf_website_service.extract_guideline_metadata_from_detail_page(
            str(detail_page_url),
        )
        guideline_entry_object = awmf_website_service.transform_extracted_metadata_to_guideline_entry(
            awmf_extracted_guideline_metadata,
        )
        created_guideline = guideline_service.create_guideline(guideline_entry_object)
        pdf_url = awmf_extracted_guideline_metadata.download_url
        if not pdf_url:
            raise ValueError("No PDF URL provided in extracted metadata.")
        
        created_guideline = awmf_documents_service.download_and_store_guideline_pdf(
            guideline=created_guideline,
            url=str(pdf_url),
            download_date=datetime.now(timezone.utc),
            overwrite_existing=True,
            remove_old_file=True,
        )
        
        created_guideline = guideline_service.update_guideline(created_guideline.id, created_guideline)
        return created_guideline
    
    except WebsiteNotAsExpectedError as e:
        raise HTTPException(status_code=422, detail={"url": e.url, "reason": e.message})
    
    except GuidelineNotFoundError as e:
        if 'created_guideline' in locals():
            try:
                # noinspection PyUnboundLocalVariable
                guideline_service.delete_guideline(created_guideline.id)
                awmf_documents_service.delete_guideline_pdf(created_guideline.download_information.file_path)
            except Exception as cleanup_error:
                raise HTTPException(
                    status_code=500, detail=f"Failed to create guideline and cleanup failed: {cleanup_error}",
                ) from e
        raise e
    
    except Exception as e:
        # If any step fails, ensure rollback of the inserted guideline
        if 'created_guideline' in locals():
            try:
                # noinspection PyUnboundLocalVariable
                guideline_service.delete_guideline(created_guideline.id)
            except Exception as cleanup_error:
                raise HTTPException(
                    status_code=500, detail=f"Failed to create guideline and cleanup failed: {cleanup_error}",
                ) from e
        raise HTTPException(status_code=500, detail=f"Failed to create guideline: {str(e)}")


# !!! IMPORTANT NOTE FOR ORDER:
# - To make guideline ids resolvable, they need to be placed behind every other endpoint
# - Else the system tries to resolve paths like "/unlinked-pdfs" into an id


@guideline_router.get("/{guideline_id}", response_model=GuidelineEntry)
def get_guideline_by_id(
        guideline_id: str, service: GuidelineService = Depends(get_guideline_service),
):
    """
    Fetch a guideline by its ID.
    """
    try:
        return service.get_guideline_by_id(guideline_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@guideline_router.put("/{guideline_id}", status_code=status.HTTP_200_OK, response_model=GuidelineEntry)
def update_guideline(
        guideline_id: str, guideline: GuidelineEntry, service: GuidelineService = Depends(get_guideline_service),
):
    """
    Update an existing guideline by its ID.
    
    Returns:
        The updated GuidelineEntry object.
    """
    try:
        updated_guideline = service.update_guideline(guideline_id, guideline)
        return updated_guideline
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@guideline_router.delete("/{guideline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_guideline(
        guideline_id: str,
        remove_pdf: bool = Query(True, description="Whether to remove the PDF file associated with the guideline."),
        delete_references: bool = Query(
            False,
            description="Whether to delete any associated references. If false, will fail if guideline has references.",
        ),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        guideline_reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
        awmf_documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
):
    """
    Delete a guideline by its ID.
    """
    try:
        guideline = guideline_service.get_guideline_by_id(guideline_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    
    references = guideline_reference_service.get_all_references(guideline_id=guideline_id)
    
    if len(references) > 0 and not delete_references:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Guideline has associated references. Set delete_references=True to delete anyway.",
        )
    
    deleted_count = None
    if len(references) > 0:
        try:
            deleted_count, deleted_reference_ids = guideline_reference_service.delete_references_by_guideline_id(
                guideline_id,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete associated references: {str(e)}",
            )
        remaining_references = [
            ref_id for ref_id in [reference.id for reference in references]
            if ref_id not in deleted_reference_ids
        ]
        if len(remaining_references) > 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete associated references, with the following reference IDs remaining: {remaining_references}",
            )
    
    try:
        if remove_pdf:
            awmf_documents_service.delete_pdf_file_if_exists(guideline)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove associated PDF file -> reason: {str(e)}",
        )
    
    # Delete the guideline
    guideline_service.delete_guideline(guideline_id)
    return {
        "message": f"Guideline deleted successfully{f', along with {deleted_count} references.' if (deleted_count is not None) else ''}",
    }


@guideline_router.get("/{guideline_id}/pdf", response_class=FileResponse)
def get_guideline_pdf(
        guideline_id: str, guideline_service: GuidelineService = Depends(get_guideline_service),
        awmf_documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
):
    """
    Return the PDF associated with a given guideline.
    """
    try:
        guideline = guideline_service.get_guideline_by_id(guideline_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    try:
        return awmf_documents_service.get_guideline_pdf(guideline)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@guideline_router.post("/{guideline_id}/upload-pdf", status_code=status.HTTP_200_OK, response_model=GuidelineEntry)
def upload_guideline_pdf(
        guideline_id: str,
        file: UploadFile = File(..., description="The guideline PDF file to upload."),
        filename: Optional[str] = Query(None, description="Optional custom filename for storing the PDF."),
        download_date: Optional[datetime] = Query(None, description="Optional custom download date. Defaults to now."),
        overwrite_existing: bool = Query(True, description="Whether to overwrite an existing PDF if already present."),
        remove_old_file: bool = Query(
            True,
            description="Whether to remove the old PDF file stored for the guideline if it already exists (if different name, else just use overwrite).",
        ),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        awmf_documents_service: AWMFDocumentsService = Depends(get_awmf_documents_service),
):
    """
    Upload a PDF for a specific guideline and link it in the database.
    """
    try:
        guideline = guideline_service.get_guideline_by_id(guideline_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    
    updated_guideline = awmf_documents_service.upload_guideline_pdf(
        guideline, file, filename, download_date, overwrite_existing, remove_old_file,
    )
    
    try:
        updated_guideline = guideline_service.update_guideline(guideline_id, updated_guideline)
    except GuidelineNotFoundError as e:
        awmf_documents_service.delete_guideline_pdf(updated_guideline.download_information.file_path)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    
    return updated_guideline


@guideline_router.get(
    "/{guideline_id}/validate_entry", status_code=status.HTTP_200_OK, response_model=GuidelineValidationResult,
)
def validate_guideline(
        guideline_id: str, guideline_service: GuidelineService = Depends(get_guideline_service),
        guideline_validation_service: GuidelineValidationService = Depends(get_guideline_validation_service),
):
    """
    Check a guideline for validity and completeness.

    - Returns whether the guideline entry is structurally valid and complete, including file and metadata checks.
    """
    try:
        guideline = guideline_service.get_guideline_by_id(guideline_id)
    except GuidelineNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    
    return guideline_validation_service.validate_guideline(guideline)
