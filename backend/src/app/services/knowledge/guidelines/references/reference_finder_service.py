import math
import re
from typing import Optional
from typing import Tuple

import fitz  # PyMuPDF
from fitz import Page

from app.models.knowledge.guidelines import GuidelineTextReference, GuidelineEntry, ReferenceType
from app.models.knowledge.guidelines.guideline_reference_models import BoundingBox
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ReferenceFinderService:
    """
    Service layer to find references automatically in guideline PDFs.
    """
    
    @staticmethod
    def get_text(guideline: GuidelineEntry, page: int) -> str:
        """
        Extracts text from the specified page of the given guideline.

        :param guideline: The guideline object containing the PDF file path
        :param page: The page number from which text should be extracted (1-indexed)
        :return: Extracted text from the specified page
        """
        if not guideline.download_information or not guideline.download_information.file_path:
            raise ValueError("Guideline has no download information or file path")
        
        # Open the document using PyMuPDF
        doc = fitz.open(guideline.download_information.file_path, filetype="pdf")
        
        # Ensure the page number is within the valid range
        if page < 1 or page > len(doc):
            raise ValueError(f"Invalid page number: {page}. The document has {len(doc)} pages.")
        
        # Get the page object
        fitz_page = doc.load_page(page - 1)  # PyMuPDF uses 0-indexing for pages
        
        # Extract the text from the page
        text = fitz_page.get_text("text").strip()  # Extracts plain text from the page
        
        return text
    
    @staticmethod
    def _search_ignoring_hyphen_breaks(page: fitz.Page, query: str):
        # First try normal search
        search_result = page.search_for(query)
        if search_result:
            logger.debug(f"Full match: {query[:20]}... of length {len(query)}")
            return search_result
        
        # Second attempt: remove whitespaces, hyphens, etc., from both query and page content
        # Normalize the query by removing non-alphanumeric characters (hyphens, spaces)
        query_normalized = re.sub(r'[^\w]', '', query)
        
        # Extract the full text from the page + normalize
        full_text = page.get_text("text")
        full_text_normalized = re.sub(r'[^\w]', '', full_text)
        
        normalized_to_original_positions = []
        for i, char in enumerate(full_text):
            if re.match(r'[^\w]', char):
                continue
            else:
                normalized_to_original_positions.append(i)
        
        matches = []
        start = full_text_normalized.find(query_normalized)
        if start != -1:
            original_start = normalized_to_original_positions[start]
            original_end = normalized_to_original_positions[start + len(query_normalized) - 1]
            
            match_text = full_text[original_start:original_end + 1]
            match_rect = page.search_for(match_text)
            matches.extend(match_rect)
            logger.debug(f"Found match with full text: {match_text[:20]}... of length {len(match_text)}")
            logger.debug(match_rect)
        
        return matches
    
    def _longest_prefix_match_on_page(self, page: fitz.Page, query: str, min_chars: int = 1, max_chars: Optional[int] = None):
        max_len = max_chars or min(len(query), len(page.get_text("text")))
        best_hits, best_l = [], 0
        for l in range(min_chars, max_len + 1, 1):
            prefix = query[:l]
            hits = self._search_ignoring_hyphen_breaks(page, prefix)
            if not hits:
                break
            else:
                best_hits, best_l = hits, l
        
        if best_hits:
            x0s, y0s, x1s, y1s = zip(*best_hits)
            mx0, my0, mx1, my1 = min(x0s), min(y0s), max(x1s), max(y1s)
            return best_l, BoundingBox(page=page.number, positions=(mx0, my0, mx1, my1))
        else:
            return 0, None
    
    def find_text_reference(
            self, guideline: GuidelineEntry, query: str, start_page: int = 0, end_page: Optional[int] = None,
    ) -> Optional[GuidelineTextReference]:
        if not guideline.download_information or not guideline.download_information.file_path:
            raise ValueError("Guideline has no download information or file path")
        
        query_normalized = query.strip()
        logger.info(f"Searching for text: '{query_normalized[:30]}' in guideline {guideline.id} ({guideline.title})")
        doc = fitz.open(guideline.download_information.file_path, filetype="pdf")
        
        bboxs = []
        remaining_query = query
        start_page_idx = start_page
        iteration = 1
        
        while remaining_query:
            logger.info(f"Search iteration {iteration}, remaining query: '{remaining_query[:30]}'")
            found = False
            best_match_len = 0
            best_match_bbox = None
            
            fallback_factor = 1.0
            max_len = None
            while math.ceil(fallback_factor * len(remaining_query)) > 0:
                min_len = max(math.ceil(fallback_factor * len(remaining_query)), best_match_len)
                
                match_len, bbox, page_idx = self._try_match_with_min_len(
                    doc, remaining_query, min_len, start_page_idx, best_match_len, end_page_idx=end_page or len(doc) - 1, max_len=max_len,
                )
                if match_len > best_match_len and bbox:
                    best_match_len, best_match_bbox = match_len, bbox
                    start_page_idx = max(page_idx - 1, start_page)
                    found = True
                    logger.info(f"New best match: {match_len} chars on page {page_idx}")
                    break  # Only try next fallback if this one fails
                if min_len == best_match_len:
                    break  # Already performed all possible better options
                
                if math.ceil(fallback_factor * len(remaining_query)) == math.ceil((fallback_factor * 2 / 3) * len(remaining_query)):
                    break  # already tried all options
                else:
                    fallback_factor = fallback_factor * 2 / 3
                    max_len = min_len
            
            if found:
                bboxs.append(best_match_bbox)
                logger.info(f"Matched '{remaining_query[:best_match_len]}' on page {start_page_idx}")
                remaining_query = remaining_query[best_match_len:].strip()
            else:
                logger.warning(f"Stopped search. Remaining unmatched text: '{remaining_query}'")
                break
            
            iteration += 1
        
        if not bboxs:
            logger.warning("No matches found in document")
            raise ValueError("No matches found in document")
        
        logger.info(f"Successfully found {len(bboxs)} bounding boxes for query '{query}'")
        
        return GuidelineTextReference(
            type=ReferenceType.TEXT,
            guideline_id=guideline.id,
            bboxs=bboxs,
            contained_text=query,
        )
    
    def _try_match_with_min_len(
            self, doc: fitz.Document, query: str, min_len: int, start_page_idx: int, current_best_len: int, end_page_idx: int,
            max_len: Optional[int] = None,
    ) -> Tuple[int, Optional[BoundingBox], int]:
        """
        Try to match query prefix of at least min_len on any page starting from start_page_idx.
        Returns: (matched_len, bounding_box, page_index)
        """
        for page_index in range(start_page_idx, end_page_idx + 1):
            logger.debug(f"Searching page {page_index + 1} (in [{start_page_idx + 1}, {end_page_idx + 1}])")
            page: Page = doc[page_index]
            match_len, bbox = self._longest_prefix_match_on_page(page, query, min_chars=min_len, max_chars=max_len)
            if match_len > current_best_len and bbox:
                return match_len, bbox, page_index
        return 0, None, -1
