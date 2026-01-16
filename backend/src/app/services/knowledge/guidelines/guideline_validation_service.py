from datetime import datetime, timezone

from app.models.knowledge.guidelines import GuidelineValidationResult, GuidelineEntry
from app.services.knowledge.guidelines import AWMFDocumentsService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class GuidelineValidationService:
    """
    Service layer to validate Guideline entries.
    """
    
    def __init__(self, awmf_documents_service: AWMFDocumentsService):
        """
        Initialize the service with Service managing access to guideline PDFs to be validated.
        """
        self.awmf_documents_service = awmf_documents_service
    
    @staticmethod
    def _validate_required_fields(
            validation_result: GuidelineValidationResult, guideline: GuidelineEntry,
    ) -> GuidelineValidationResult:
        """
        Expectation:
        - awmf_register_number and awmf_register_number_full are required
        - title, awmf_class is required
        - There is at least one organization with is_leading=True in publishing_organizations
        """
        logger.debug(f"Validating required fields for guideline {guideline.awmf_register_number}")
        if not guideline.awmf_register_number:
            validation_result.add_error("AWMF register number is required, but missing.")
            logger.warning("AWMF register number missing")
        if not guideline.awmf_register_number_full:
            validation_result.add_error(
                "Full AWMF register number is required, but missing (can just set it to awmf_register_number).",
            )
            logger.warning("Full AWMF register number missing")
        if guideline.awmf_register_number and guideline.awmf_register_number_full:
            if guideline.awmf_register_number not in guideline.awmf_register_number_full:
                error_msg = f"AWMF register number must be contained in the full register number, but {guideline.awmf_register_number} not contained in {guideline.awmf_register_number_full}."
                validation_result.add_error(error_msg)
                logger.error(error_msg)
        if not guideline.awmf_class:
            validation_result.add_error("Guideline class is required, but missing.")
            logger.warning("Guideline class missing")
        if not guideline.title:
            validation_result.add_error("Guideline title is required, but missing.")
            logger.warning("Guideline title missing")
        if not guideline.publishing_organizations or not any(
                [
                    org.is_leading for org in guideline.publishing_organizations
                ],
        ):
            validation_result.add_error("At least one organization must be leading.")
            logger.warning("No leading organization specified")
        return validation_result
    
    @staticmethod
    def _check_keywords_complete(
            validation_result: GuidelineValidationResult, guideline: GuidelineEntry,
    ) -> GuidelineValidationResult:
        """
        Expectation:
        - No empty keywords, no duplicates
        """
        logger.debug(f"Checking keywords for guideline {guideline.awmf_register_number}")
        if not guideline.keywords or len(guideline.keywords) == 0:
            validation_result.add_warning("No keywords provided.")
            logger.warning("No keywords provided for guideline")
        
        seen_keywords = set()
        duplicates = [kw for kw in guideline.keywords if kw in seen_keywords or seen_keywords.add(kw)]
        if duplicates:
            warning_msg = f"Found duplicate keywords: {', '.join(duplicates)}"
            validation_result.add_warning(warning_msg)
            logger.warning(warning_msg)
        
        return validation_result
    
    def _validate_download_information_and_pdf(
            self, validation_result: GuidelineValidationResult, guideline: GuidelineEntry,
    ) -> GuidelineValidationResult:
        logger.debug(f"Validating download information for guideline {guideline.awmf_register_number}")
        if guideline.download_information:
            if not guideline.download_information.url:
                validation_result.add_error("Guideline download URL is required, but missing.")
                logger.error("Download URL missing")
            
            download_date, file_path, page_count = guideline.download_information.download_date, guideline.download_information.file_path, guideline.download_information.page_count
            fields = ["download_date", "file_path", "page_count"]
            values = [download_date, file_path, page_count]
            missing = [f for f, v in zip(fields, values) if v is None]
            given = [f for f, v in zip(fields, values) if v is not None]
            
            if len(given) == 0:
                validation_result.add_warning(
                    "Guideline information is incomplete (no download date, file path, and page count).",
                )
                logger.warning("All download information fields missing")
            elif len(missing) > 0:
                error_msg = f"Guideline information is incomplete [given: {given}, but missing: {missing}]."
                validation_result.add_error(error_msg)
                logger.error(error_msg)
            
            if file_path:
                logger.debug(f"Validating PDF file at {file_path}")
                pdf_validation = self.awmf_documents_service.validate_pdf_file(file_path)
                if not pdf_validation["file_exists"]:
                    error_msg = f"Given guideline PDF file {file_path} does not exist."
                    validation_result.add_error(error_msg)
                    logger.error(error_msg)
                else:
                    if not pdf_validation["file_valid"]:
                        error_msg = f"Guideline PDF file {file_path} exists, but is not valid (cannot be opened / is no PDF / ...)."
                        validation_result.add_error(error_msg)
                        logger.error(error_msg)
                    elif page_count and (page_count != pdf_validation["page_count"]):
                        error_msg = f"Guideline PDF page count ({pdf_validation['page_count']}) does not match expected ({page_count})."
                        validation_result.add_error(error_msg)
                        logger.error(error_msg)
        
        else:
            error_msg = "Guideline download information is required, but missing (add at least the URL from which guideline should be downloaded)."
            validation_result.add_error(error_msg)
            logger.error(error_msg)
        return validation_result
    
    def _validate_validity_information(
            self, validation_result: GuidelineValidationResult, guideline: GuidelineEntry,
    ) -> GuidelineValidationResult:
        logger.debug(f"Validating validity information for guideline {guideline.awmf_register_number}")
        if guideline.validity_information:
            creation_date = guideline.validity_information.guideline_creation_date
            valid_flag = guideline.validity_information.valid
            validity_range = guideline.validity_information.validity_range
            
            if creation_date:
                today = datetime.now(timezone.utc)
                valid_until_expected = creation_date.replace(year=creation_date.year + validity_range)
                if (valid_until_expected >= today) and not valid_flag:
                    error_msg = f"Guideline is valid till {valid_until_expected} (for {validity_range} years), but valid flag is set to False."
                    validation_result.add_error(error_msg)
                    logger.error(error_msg)
                if (valid_until_expected < today) and valid_flag:
                    error_msg = f"Guideline is valid till {valid_until_expected} (for {validity_range} years), but valid flag is set to True."
                    validation_result.add_error(error_msg)
                    logger.error(error_msg)
            else:
                validation_result.add_error("Guideline creation date missing in validity information.")
                logger.error("Guideline creation date missing")
        else:
            validation_result.add_warning("Validity information missing.")
            logger.warning("Validity information missing")
        return validation_result
    
    def validate_guideline(self, guideline: GuidelineEntry) -> GuidelineValidationResult:
        logger.info(f"Starting validation for guideline {guideline.awmf_register_number}")
        validation_result = GuidelineValidationResult()
        validation_result = self._validate_required_fields(validation_result, guideline)
        validation_result = self._check_keywords_complete(validation_result, guideline)
        validation_result = self._validate_download_information_and_pdf(validation_result, guideline)
        validation_result = self._validate_validity_information(validation_result, guideline)
        logger.info(f"Completed validation for guideline {guideline.awmf_register_number}")
        return validation_result
