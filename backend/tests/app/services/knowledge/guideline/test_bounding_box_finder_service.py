import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import fitz
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

from app.models.knowledge.guideline import (  # noqa: E402
    GuidelineDownloadInformation,
    GuidelineEntry,
    GuidelineValidityInformation,
    OrganizationEntry,
)
from app.services.knowledge.guideline.bounding_box_finder_service import BoundingBoxFinderService  # noqa: E402

ASSETS_DIR = Path(__file__).resolve().parents[4] / "assets"
BOUNDING_BOX_FIXTURE_PDF = ASSETS_DIR / "bounding_box_finder_fixture.pdf"


class BoundingBoxFinderServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = BoundingBoxFinderService()
    
    def test_finds_cross_page_text_despite_header_noise(self):
        search_text = (
            "Die Relevanz der chirurgischen Komplikationen zeigt sich auch anhand "
            "der hohen Zahl von Schadenhaftungsfaellen"
        )
        
        with self._temporary_guideline_pdf() as guideline:
            with fitz.open(guideline.download_information.file_path) as doc:
                first_page = doc[0]
                first_page.insert_text((72, 90), "Die Relevanz der chirurgischen Komplikationen zeigt")
                
                second_page = doc.new_page()
                second_page.insert_text((72, 40), "S3-Leitlinie")
                second_page.insert_text((72, 58), "Operative Entfernung von Weisheitszaehnen")
                second_page.insert_text((72, 76), "Langversion Stand August 2019")
                second_page.insert_text(
                    (72, 170),
                    "sich auch anhand der hohen Zahl von Schadenhaftungsfael len",
                )
                
                doc.saveIncr()
            
            bboxs = self.service.text_to_bounding_boxes(guideline, search_text, start_page=1, end_page=2)
        
        self.assertEqual([bbox.page for bbox in bboxs], [1, 2])
    
    def test_splits_boxes_when_unrelated_footnote_interrupts_same_page(self):
        search_text = (
            "Die Relevanz der chirurgischen Komplikationen zeigt sich auch anhand "
            "der hohen Zahl von Schadenhaftungsfaellen"
        )
        
        with self._temporary_guideline_pdf() as guideline:
            with fitz.open(guideline.download_information.file_path) as doc:
                page = doc[0]
                page.insert_text((72, 90), "Die Relevanz der chirurgischen Komplikationen zeigt")
                page.insert_text((72, 260), "1 Fussnote mit anderem Inhalt, der ignoriert werden soll.")
                page.insert_text((72, 520), "sich auch anhand der hohen Zahl von Schadenhaftungsfael len")
                doc.saveIncr()
            
            bboxs = self.service.text_to_bounding_boxes(guideline, search_text, start_page=1, end_page=1)
        
        self.assertEqual(len(bboxs), 2)
        self.assertTrue(all(bbox.page == 1 for bbox in bboxs))
        self.assertLess(bboxs[0].positions[3], bboxs[1].positions[1])
    
    @unittest.skipUnless(BOUNDING_BOX_FIXTURE_PDF.exists(), "Add tests/assets/bounding_box_finder_fixture.pdf to enable.")
    def test_asset_pdf_fixture_is_available_for_real_world_regressions(self):
        self.assertTrue(BOUNDING_BOX_FIXTURE_PDF.exists())
    
    @staticmethod
    def _build_guideline(pdf_path: str) -> GuidelineEntry:
        return GuidelineEntry(
            _id=ObjectId(),
            awmf_register_number="007-001",
            awmf_register_number_full="007-001",
            title="Test Guideline",
            publishing_organizations=[OrganizationEntry(name="Org", is_leading=True)],
            download_information=GuidelineDownloadInformation(url="https://example.com/test.pdf", file_path=pdf_path),
            validity_information=GuidelineValidityInformation(
                version="1.0",
                guideline_creation_date=date(2025, 1, 1),
                valid=True,
                extended_validity=False,
                validity_range=5,
            ),
        )
    
    @staticmethod
    def _temporary_guideline_pdf():
        class _GuidelinePdfContext:
            def __enter__(self_inner):
                self_inner.temp_dir = tempfile.TemporaryDirectory()
                self_inner.pdf_path = str(Path(self_inner.temp_dir.name) / "guideline.pdf")
                doc = fitz.open()
                doc.new_page()
                doc.save(self_inner.pdf_path)
                doc.close()
                return BoundingBoxFinderServiceTest._build_guideline(self_inner.pdf_path)
            
            def __exit__(self_inner, exc_type, exc_val, exc_tb):
                self_inner.temp_dir.cleanup()
        
        return _GuidelinePdfContext()


if __name__ == "__main__":
    unittest.main()
