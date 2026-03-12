from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF

from app.exceptions.knowledge.guideline import TextInGuidelineNotFoundError
from app.models.knowledge.guideline import BoundingBox, GuidelineEntry


@dataclass
class BoundingBoxFinderService:
    """Service for finding bounding boxes in a guideline document."""
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text slightly to improve matching robustness."""
        return " ".join(text.split()).strip()
    
    @staticmethod
    def _get_pdf_path(guideline: GuidelineEntry) -> Path:
        pdf_path = guideline.download_information.file_path
        if not pdf_path:
            raise ValueError("Guideline does not contain a PDF file path.")
        
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        return pdf_path
    
    def get_page_text(self, guideline: GuidelineEntry, page: int) -> str:
        """Return the full text of a specific PDF page.

        Page numbering is 1-based.
        """
        pdf_path = self._get_pdf_path(guideline)
        
        with fitz.open(pdf_path) as doc:
            if page < 1 or page > len(doc):
                raise ValueError(
                    f"Page {page} is out of range. PDF has {len(doc)} pages.",
                )
            
            pdf_page = doc[page - 1]
            return pdf_page.get_text("text")
    
    def text_to_bounding_boxes(
            self,
            guideline: GuidelineEntry,
            text: str,
            start_page: Optional[int] = None,
            end_page: Optional[int] = None,
    ) -> List[BoundingBox]:
        """Find text in the guideline PDF and return matching bounding boxes.

        - Page numbering is 1-based.
        - `start_page` and `end_page` are inclusive.
        - If the text occurs multiple times, all matching boxes are returned.
        """
        if not text or not text.strip():
            raise ValueError("Text to search for must not be empty.")
        
        pdf_path = self._get_pdf_path(guideline)
        bboxs: List[BoundingBox] = []
        
        original_text = text.strip()
        normalized_text = self._normalize_text(text)
        
        with fitz.open(pdf_path) as doc:
            page_count = len(doc)
            
            if page_count == 0:
                raise TextInGuidelineNotFoundError("The guideline PDF contains no pages.")
            
            start_idx = 0 if start_page is None else start_page - 1
            end_idx = page_count - 1 if end_page is None else end_page - 1
            
            if start_idx < 0 or end_idx >= page_count or start_idx > end_idx:
                raise ValueError(
                    f"Invalid page range: start_page={start_page}, end_page={end_page}, "
                    f"page_count={page_count}",
                )
            
            search_flags = fitz.TEXT_DEHYPHENATE
            
            for page_index in range(start_idx, end_idx + 1):
                page = doc[page_index]
                
                rects = page.search_for(original_text, flags=search_flags)
                
                if not rects and normalized_text != original_text:
                    rects = page.search_for(normalized_text, flags=search_flags)
                
                for rect in rects:
                    bboxs.append(
                        BoundingBox(
                            page=page_index + 1,  # 1-based page numbering
                            positions=(rect.x0, rect.y0, rect.x1, rect.y1),
                        ),
                    )
        
        if not bboxs:
            raise TextInGuidelineNotFoundError(f"Could not find text in guideline '{guideline.id}': {text!r}")
        
        return bboxs
