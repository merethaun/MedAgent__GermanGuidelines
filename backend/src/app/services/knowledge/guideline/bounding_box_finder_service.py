from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from app.exceptions.knowledge.guideline import TextInGuidelineNotFoundError
from app.models.knowledge.guideline import BoundingBox, GuidelineEntry


@dataclass
class BoundingBoxFinderService:
    """Service for finding bounding boxes in a guideline document."""

    MIN_BOX_WIDTH = 5.0
    MIN_BOX_AREA = 80.0
    THIN_TALL_BOX_MAX_WIDTH = 10.0
    THIN_TALL_BOX_MIN_HEIGHT = 30.0
    SAME_LINE_Y_TOLERANCE = 3.0
    HORIZONTAL_MERGE_GAP = 8.0
    VERTICAL_MERGE_GAP = 4.0
    COLUMN_X_TOLERANCE = 2.0
    BLOCK_X_OVERLAP_TOLERANCE = 2.0
    
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

    @staticmethod
    def _merge_positions(
            rects: List[Tuple[float, float, float, float]],
    ) -> List[Tuple[int, int, int, int]]:
        """Merge rectangles that likely belong to the same text block."""
        rects = [rect for rect in rects if BoundingBoxFinderService._is_meaningful_rect(rect)]

        if not rects:
            return []

        merged_rects = sorted(rects, key=lambda rect: (rect[1], rect[0], rect[3], rect[2]))

        changed = True
        while changed:
            changed = False
            next_rects: List[Tuple[float, float, float, float]] = []

            for rect in merged_rects:
                merged = False

                for idx, existing in enumerate(next_rects):
                    if BoundingBoxFinderService._should_merge_rects(existing, rect):
                        next_rects[idx] = BoundingBoxFinderService._combine_rects(existing, rect)
                        merged = True
                        changed = True
                        break

                if not merged:
                    next_rects.append(rect)

            merged_rects = sorted(next_rects, key=lambda rect: (rect[1], rect[0], rect[3], rect[2]))

        return [
            (
                int(round(rect[0])),
                int(round(rect[1])),
                int(round(rect[2])),
                int(round(rect[3])),
            )
            for rect in merged_rects
        ]

    @classmethod
    def _is_meaningful_rect(cls, rect: Tuple[float, float, float, float]) -> bool:
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        area = width * height

        if width < cls.MIN_BOX_WIDTH:
            return False

        if area < cls.MIN_BOX_AREA:
            return False

        if width <= cls.THIN_TALL_BOX_MAX_WIDTH and height >= cls.THIN_TALL_BOX_MIN_HEIGHT:
            return False

        return True

    @classmethod
    def _should_merge_rects(
            cls,
            left: Tuple[float, float, float, float],
            right: Tuple[float, float, float, float],
    ) -> bool:
        left_x0, left_y0, left_x1, left_y1 = left
        right_x0, right_y0, right_x1, right_y1 = right

        horizontal_gap = max(0.0, max(right_x0 - left_x1, left_x0 - right_x1))
        vertical_gap = max(0.0, max(right_y0 - left_y1, left_y0 - right_y1))

        left_center_y = (left_y0 + left_y1) / 2
        right_center_y = (right_y0 + right_y1) / 2
        same_line = (
            abs(left_center_y - right_center_y) <= cls.SAME_LINE_Y_TOLERANCE
            and vertical_gap <= cls.SAME_LINE_Y_TOLERANCE
        )

        same_column = (
            abs(left_x0 - right_x0) <= cls.COLUMN_X_TOLERANCE
            and abs(left_x1 - right_x1) <= cls.COLUMN_X_TOLERANCE
            and vertical_gap <= cls.VERTICAL_MERGE_GAP
        )

        overlapping_block = (
            min(left_x1, right_x1) - max(left_x0, right_x0) >= -cls.BLOCK_X_OVERLAP_TOLERANCE
            and vertical_gap <= cls.VERTICAL_MERGE_GAP
        )

        return (same_line and horizontal_gap <= cls.HORIZONTAL_MERGE_GAP) or same_column or overlapping_block

    @staticmethod
    def _combine_rects(
            first: Tuple[float, float, float, float],
            second: Tuple[float, float, float, float],
    ) -> Tuple[float, float, float, float]:
        return (
            min(first[0], second[0]),
            min(first[1], second[1]),
            max(first[2], second[2]),
            max(first[3], second[3]),
        )
    
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
                page_rects: List[Tuple[float, float, float, float]] = []
                
                rects = page.search_for(original_text, flags=search_flags)
                
                if not rects and normalized_text != original_text:
                    rects = page.search_for(normalized_text, flags=search_flags)
                
                for rect in rects:
                    page_rects.append((rect.x0, rect.y0, rect.x1, rect.y1))

                for merged_rect in self._merge_positions(page_rects):
                    bboxs.append(
                        BoundingBox(
                            page=page_index + 1,  # 1-based page numbering
                            positions=merged_rect,
                        ),
                    )
        
        if not bboxs:
            raise TextInGuidelineNotFoundError(f"Could not find text in guideline '{guideline.id}': {text!r}")
        
        return bboxs
