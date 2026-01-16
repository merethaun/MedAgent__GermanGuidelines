from datetime import date
from typing import List, Optional

from pydantic import BaseModel, HttpUrl, Field


class AWMFExtractedGuidelineMetadata(BaseModel):
    guideline_details_website: HttpUrl = Field(..., description="URL to the full metadata detail page")
    awmf_register_number: str = Field(..., description="Short AWMF register number (format: ddd-ddd)")
    title: str = Field(..., description="Official title of the guideline")
    awmf_class: str = Field(..., description="Guideline class (e.g., S1, S2k, S3)")
    download_url: HttpUrl = Field(..., description="URL to the PDF file")
    version: str = Field(..., description="Version of the guideline if available")
    date_of_guideline_creation: date = Field(..., description="Date the guideline was officially published")
    date_until_valid: date = Field(..., description="Date until the guideline is valid (optional)")
    
    leading_publishing_organizations: List[str] = Field(
        default_factory=list, description="List of leading publisher organizations",
    )
    further_organizations: List[str] = Field(
        default_factory=list, description="Additional contributors or co-publishers",
    )
    
    keywords: List[str] = Field(default_factory=list, description="Keywords related to the guideline")
    goal: Optional[str] = Field(None, description="Goal or general description of the guideline")
    target_patients: Optional[str] = Field(None, description="Target patient group for the guideline")
    care_area: Optional[str] = Field(None, description="Medical care context or area the guideline applies to")


class AWMFSearchResult(BaseModel):
    extracted_guideline_pdf_urls: List[HttpUrl] = Field(
        default_factory=list, description="List of URLs to detail pages with guideline PDF files",
        examples=[[HttpUrl("https://register.awmf.org/de/leitlinien/detail/007-007")]],
    )
    extracted_guideline_registration_urls: List[HttpUrl] = Field(
        default_factory=list,
        description="List of URLs to guideline registration pages (no guideline PDF yet, so guideline likely not fully defined but yet to be created and published)",
        examples=[[HttpUrl("https://register.awmf.org/de/leitlinien/detail/075-002#anmeldung")]],
    )
    valid_found: int = Field(
        ..., description="Number of detail URLs (where we can expect a guideline PDF) successfully extracted",
        examples=[1],
    )
    non_pdf_found: int = Field(
        ..., description="Number of detail URLs (where we can expect a guideline PDF) that did not yield a PDF",
        examples=[1],
    )
    expected_count: int = Field(
        ..., description="Expected result count from page (listed number of hits)",
        examples=[2],
    )
