import glob
import os
import shutil
from datetime import datetime, timezone
from typing import Optional, Dict, List, Union

import requests
from fastapi import UploadFile
from fastapi.responses import FileResponse
from pypdf import PdfReader

from app.constants.mongodb_constants import GUIDELINE_PDFS_FOLDER
from app.models.knowledge.guidelines import GuidelineEntry, GuidelineDownloadInformation
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AWMFDocumentsService:
    """
    Service layer to manage interactions with AWMF-guideline documents (PDFs)
    """
    
    def download_and_store_guideline_pdf(
            self, guideline: GuidelineEntry, url: str, filename: Optional[str] = None,
            download_date: Optional[datetime] = None, overwrite_existing: Optional[bool] = True,
            remove_old_file: Optional[bool] = True,
    ) -> GuidelineEntry:
        """
        Downloads a PDF from a given URL, stores it locally, and updates the guideline's download_information.

        - If a previous file exists:
            - If `overwrite_existing` is False: raise error.
            - If `overwrite_existing` is True: optionally remove the old file (if the name changes).
        """
        logger.debug(f"Starting download of guideline PDF from {url}")
        os.makedirs(GUIDELINE_PDFS_FOLDER, exist_ok=True)
        
        # Define file path
        safe_filename = filename if filename else f"{guideline.id}.pdf"
        file_path = os.path.join(GUIDELINE_PDFS_FOLDER, safe_filename)
        download_date = download_date or datetime.now(timezone.utc)
        logger.debug(f"Using file path: {file_path}")
        
        # Check for file collision
        if os.path.exists(file_path):
            if not overwrite_existing:
                logger.error(f"File collision detected at {file_path} and overwriting not allowed")
                raise ValueError(f"File '{file_path}' already exists and overwriting is not allowed.")
            logger.debug(f"Overwriting existing file: {file_path}")
        
        # Remove old file if necessary
        current_file_path = guideline.download_information.file_path if guideline.download_information else None
        if current_file_path and current_file_path != file_path and os.path.exists(current_file_path):
            if remove_old_file:
                logger.info(f"Removing old guideline PDF: {current_file_path}")
                os.remove(current_file_path)
        
        # Download the new PDF
        try:
            logger.debug(f"Initiating download from {url}")
            response = requests.get(url)
            if response.status_code != 200:
                logger.error(f"Failed to download PDF, status code: {response.status_code}")
                raise RuntimeError(f"Failed to download PDF from {url} (status: {response.status_code})")
            
            with open(file_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Saved PDF to {file_path}")
            
            page_count = self.get_page_count(file_path)
            if page_count == 0:
                logger.error("Downloaded PDF appears to be empty")
                raise ValueError("Downloaded PDF appears empty.")
            logger.debug(f"PDF validated with {page_count} pages")
        
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            logger.error(f"Failed to download and store guideline PDF: {e}")
            raise
        
        # Update the guideline entry
        logger.debug("Updating guideline entry with download information")
        if not guideline.download_information:
            guideline.download_information = GuidelineDownloadInformation(
                url=url,
                download_date=download_date,
                file_path=file_path,
                page_count=page_count,
            )
        else:
            guideline.download_information.url = url
            guideline.download_information.file_path = file_path
            guideline.download_information.download_date = download_date
            guideline.download_information.page_count = page_count
        
        logger.info(f"Successfully downloaded and stored guideline PDF with {page_count} pages")
        return guideline
    
    def upload_guideline_pdf(
            self, guideline: GuidelineEntry, file: UploadFile, filename: Optional[str] = None,
            download_date: Optional[datetime] = None, overwrite_existing: Optional[bool] = True,
            remove_old_file: Optional[bool] = True,
    ) -> GuidelineEntry:
        """
        Saves the uploaded PDF file and return the GuidelineEntry with updated download_information.
        
        - If a previous file exists:
            - If `overwrite_existing` is False: raise error.
            - If `overwrite_existing` is True: optionally remove the old file (if the name changes).
        """
        logger.debug(f"Starting PDF upload for guideline {guideline.id}")
        if file.content_type != "application/pdf":
            logger.error(f"Invalid file type: {file.content_type}")
            raise ValueError("Uploaded file must be a PDF.")
        
        os.makedirs(GUIDELINE_PDFS_FOLDER, exist_ok=True)
        filename, _ = os.path.splitext(filename)
        file_path = os.path.join(GUIDELINE_PDFS_FOLDER, f"{filename if filename else guideline.id}.pdf")
        download_date = download_date if download_date else datetime.now(timezone.utc)
        logger.debug(f"Using file path: {file_path}")
        
        if os.path.exists(file_path):
            if not overwrite_existing:
                logger.error(f"File collision detected at {file_path} and overwriting not allowed")
                raise ValueError(f"File '{file_path}' already exists and overwriting is not allowed.")
            else:
                logger.debug(f"Overwriting existing file: {file_path}")
        
        current_file_path = guideline.download_information.file_path if guideline.download_information else None
        if current_file_path and current_file_path != file_path and os.path.exists(current_file_path):
            if remove_old_file:
                logger.info(f"Removing old guideline PDF: {current_file_path}")
                os.remove(current_file_path)
        
        try:
            logger.debug("Starting file copy operation")
            with open(file_path, "wb") as buffer:
                # noinspection PyTypeChecker
                shutil.copyfileobj(file.file, buffer)
            logger.info(f"Successfully saved uploaded file to {file_path}")
            
            page_count = self.get_page_count(file_path)
            if page_count == 0:
                logger.error("Uploaded PDF appears to be empty")
                raise ValueError("Uploaded PDF is empty.")
            logger.debug(f"PDF validated with {page_count} pages")
        
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            logger.error(f"Failed to save uploaded guideline PDF: {e}")
            raise
        
        logger.debug("Updating guideline entry with upload information")
        if not guideline.download_information:
            guideline.download_information = GuidelineDownloadInformation(
                url="local_upload",
                download_date=download_date,
                file_path=file_path,
                page_count=page_count,
            )
        else:
            guideline.download_information.file_path = file_path
            guideline.download_information.download_date = download_date
            guideline.download_information.page_count = page_count
        
        logger.info(f"Successfully processed uploaded PDF with {page_count} pages")
        return guideline
    
    def get_page_count(self, file_path) -> int:
        logger.debug(f"Getting page count for {file_path}")
        try:
            with open(file_path, 'rb') as f:
                reader = PdfReader(f)
                count = len(reader.pages)
                logger.debug(f"PDF has {count} pages")
                return count
        except Exception as e:
            logger.error(f"Failed to read PDF {file_path}: {str(e)}")
            raise ValueError(f"Failed to read PDF: {str(e)}")
    
    def delete_guideline_pdf(self, file_path: str):
        logger.debug(f"Attempting to delete PDF at {file_path}")
        try:
            os.remove(file_path)
            logger.info(f"Successfully deleted PDF at {file_path}")
        except FileNotFoundError as e:
            logger.warning(f"PDF file not found: {str(e)}, so was already deleted.")
        except Exception as e:
            logger.error(f"Failed to delete PDF at {file_path}: {str(e)}")
            raise ValueError(f"Failed to delete PDF: {str(e)}")
    
    def validate_pdf_file(self, file_path: str) -> Dict[str, Union[bool, int]]:
        """
        Validates PDF file existence / readability and checks page count.

        :param file_path: Path to PDF file
        :return: Dict with validation results:
            - "file_exists": bool - if file exists
            - "file_valid": bool - if file is valid PDF (can be read)
            - "page_count": int - (-1) if no file or invalid file, else the page count of the PDF
        """
        logger.debug(f"Starting validation of PDF at {file_path}")
        if not os.path.exists(file_path):
            logger.warning(f"PDF file does not exist at {file_path}")
            return {"file_exists": False, "file_valid": False, "page_count": -1}
        
        try:
            with open(file_path, 'rb') as f:
                reader = PdfReader(f)
                actual_pages = len(reader.pages)
                logger.debug(f"Successfully validated PDF with {actual_pages} pages")
                return {"file_exists": True, "file_valid": True, "page_count": actual_pages}
        except Exception as e:
            logger.error(f"Failed to read PDF {file_path} while validation: {str(e)}")
            return {"file_exists": True, "file_valid": False, "page_count": -1}
    
    def get_guideline_pdf(self, guideline: GuidelineEntry) -> FileResponse:
        """Gets a PDF file from guideline entry and returns as FileResponse.
    
        Args:
            guideline: GuidelineEntry with a PDF file path
        
        Returns:
            FileResponse serving the PDF file
        
        Raises:
            FileNotFoundError: If file path invalids or files not found
        """
        file_path = guideline.download_information.file_path
        logger.debug(f"Attempting to serve PDF from {file_path}")
        if not file_path or not os.path.exists(file_path):
            logger.error(f"PDF not found at path: {file_path}")
            raise FileNotFoundError(f"PDF not found at path: {file_path}")
        
        logger.info(f"Serving PDF file: {file_path}")
        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=os.path.basename(file_path),
        )
    
    def delete_pdf_file_if_exists(self, guideline: GuidelineEntry):
        logger.debug(f"Checking for PDF file to delete for guideline {guideline.id}")
        if guideline.download_information and guideline.download_information.file_path:
            logger.debug(f"Found PDF file path: {guideline.download_information.file_path}")
            self.delete_guideline_pdf(guideline.download_information.file_path)
        else:
            logger.warning(f"No PDF file found for guideline {guideline.id}.")
    
    def get_all_pdfs_in_storage_location(self) -> List[str]:
        """Get all PDF files from the guideline PDF storage location as absolute paths."""
        logger.debug("Scanning storage location for PDF files")
        search_pattern = os.path.join(GUIDELINE_PDFS_FOLDER, '**', '*.pdf')
        pdf_files = glob.glob(search_pattern, recursive=True)
        abs_paths = [os.path.abspath(f) for f in pdf_files if os.path.isfile(f)]
        logger.debug(f"Found {len(abs_paths)} PDF files in storage")
        return abs_paths
    
    def get_unlinked_pdf_files(self, all_guidelines: List[GuidelineEntry]) -> List[str]:
        """Get PDF files that are not referenced by any guideline entry.
        
        Args:
            all_guidelines: List of GuidelineEntry objects
            
        Returns:
            List of unreferenced PDFs (absolute file paths)
        """
        logger.debug("Starting search for unlinked PDF files")
        referenced = {
            os.path.abspath(g.download_information.file_path)
            for g in all_guidelines
            if g.download_information and g.download_information.file_path
        }
        logger.debug(f"Found {len(referenced)} referenced PDF files")
        
        all_pdfs = self.get_all_pdfs_in_storage_location()
        unlinked = [pdf for pdf in all_pdfs if pdf not in referenced]
        logger.debug(f"Found {len(unlinked)} unlinked PDFs in storage location.")
        return unlinked
    
    def remove_unlinked_pdf_files(self, all_guidelines) -> int:
        logger.info("Starting removal of unlinked PDF files")
        unlinked_pdfs = self.get_unlinked_pdf_files(all_guidelines)
        for pdf in unlinked_pdfs:
            self.delete_guideline_pdf(pdf)
        logger.info(f"Removed {len(unlinked_pdfs)} unlinked PDFs from storage location.")
        return len(unlinked_pdfs)
