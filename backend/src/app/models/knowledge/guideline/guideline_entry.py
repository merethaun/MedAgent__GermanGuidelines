from datetime import datetime, date
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, model_serializer

from app.models.common.py_object_id import PyObjectId
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class OrganizationEntry(BaseModel):
    """
    Represents an organization associated with a guideline (e.g., publisher).
    """
    name: str = Field(..., description="Name of the organization", examples=["German Society for Oral Surgery"])
    is_leading: bool = Field(..., description="Whether this organization was a leading publisher", examples=[True])


class GuidelineDownloadInformation(BaseModel):
    """
    Contains metadata about the downloaded guideline PDF.
    """
    url: str = Field(
        ...,
        description="URL from which the PDF was downloaded",
        examples=[
            "https://register.awmf.org/assets/guidelines/007-106l_S3_Totaler_alloplastischer_Kiefergelenkersatz.pdf",
        ],
    )
    download_date: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the guideline was downloaded",
        examples=["2025-04-14T16:05:25.380705"],
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Local path to the downloaded guideline PDF",
        examples=["output/guideline/pdf/007-106l_S3_Totaler_alloplastischer_Kiefergelenkersatz.pdf"],
    )
    page_count: Optional[int] = Field(
        default=None,
        description="Total page count of the guideline PDF",
        examples=[152],
    )


class GuidelineValidityInformation(BaseModel):
    """
    Contains information about the validity of a guideline.
    """
    version: str = Field(description="Version of the guideline (either as provided on the publication page OR just the date of guideline creation)")
    guideline_creation_date: date = Field(..., description="Publication date of the guideline", examples=["2025-04-01"])
    valid: bool = Field(..., description="True if guideline is still within official validity period", examples=[False])
    extended_validity: bool = Field(
        ...,
        description="True if validity was officially extended beyond original expiration",
        examples=[False],
    )
    validity_range: int = Field(
        default=5,
        description="Validity range in years; default is 5 years, 1 year for living guidelines",
        examples=[5],
    )
    
    @model_serializer(mode='plain')
    def serialize(self):
        data = self.__dict__.copy()
        gl_c_d = data.get("guideline_creation_date", None)
        if gl_c_d and isinstance(gl_c_d, date) and not isinstance(gl_c_d, datetime):
            data["guideline_creation_date"] = datetime.combine(data["guideline_creation_date"], datetime.min.time())
        return data


class GuidelineEntry(BaseModel):
    """
    Represents a medical guideline entry stored in the system.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID (ObjectId as string)")
    awmf_register_number: str = Field(..., description="AWMF register number (format: 'ddd-ddd')", examples=["007-106"])
    awmf_register_number_full: str = Field(
        ...,
        description="Full AWMF register number including optional letters (e.g., '007-106l')",
        examples=["007-106l"],
    )
    awmf_class: Optional[str] = Field(default=None, description="Guideline class (e.g., S1, S2k, S3)", examples=["S3"])
    title: str = Field(
        ...,
        description="Official title of the guideline",
        examples=["Totaler alloplastischer Kiefergelenkersatz"],
    )
    publishing_organizations: List[OrganizationEntry] = Field(
        ...,
        description="List of organizations involved in publishing the guideline",
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Keywords related to the guideline (manually assigned or extracted)",
        examples=[["Kiefergelenkprothese", "Komplikationen", "jaw replacement"]],
    )
    goal: Optional[str] = Field(
        None,
        description="Goal or general description of the guideline",
        examples=[
            "Die Leitlinie „Operative Entfernung von Weisheitszähnen“ soll eine evidenzbasierte Grundlage für die häufige ...",
        ],
    )
    target_patients: Optional[str] = Field(
        None,
        description="Target patient group for the guideline",
        examples=["Zielgruppe sind alle Menschen mit Weisheitszähnen", "Kinder und Erwachsene"],
    )
    care_area: Optional[str] = Field(
        None,
        description="Medical care context or area the guideline applies to",
        examples=[
            "Die Versorgung findet überwiegend ambulant statt.",
            "Ambulante und stationäre Versorgung, Spezialärztliche Therapie",
        ],
    )
    download_information: GuidelineDownloadInformation
    validity_information: GuidelineValidityInformation
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_by_name=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "awmf_register_number": "007-106",
                "awmf_register_number_full": "007-106l",
                "awmf_class": "S3",
                "title": "Totaler alloplastischer Kiefergelenkersatz",
                "publishing_organizations": [
                    {
                        "name": "Deutsche Gesellschaft für Mund-, Kiefer- und Gesichtschirurgie e.V. (DGMKG)",
                        "is_leading": True,
                    },
                    {
                        "name": "Deutsche Gesellschaft für Kieferorthopädie e.V. (DGKFO)",
                        "is_leading": False,
                    },
                ],
                "keywords": [
                    "Kiefergelenkprothese", "alloplastischer Kiefergelenkersatz", "Komplikationen",
                ],
                "goal": "Angesichts des wachsenden Interesses für den totalen alloplastischen Kiefergelenkersatz und der eingeschränkten Datenlage ...",
                "target_patients": "Die Leitlinie betrifft alle Patientengruppen mit totalem alloplastischen Kiefergelenkersatz (ausgenommen sind der autologe sowie der partielle Kiefergelenkersatz) in Deutschland ...",
                "care_area": "Der Versorgungsbereich entspricht der stationären und gegebenenfalls ambulanten Versorgung in Deutschland bzw. im deutschsprachigen Raum und betrifft Diagnostik, Therapie und Nachsorge",
                "download_information": {
                    "url": "https://register.awmf.org/assets/guidelines/007-106l_S3_Totaler_alloplastischer_Kiefergelenkersatz.pdf",
                    "download_date": "2025-04-14T16:05:25.380705",
                    "file_path": "output/guideline/pdf/007-106l_S3_Totaler_alloplastischer_Kiefergelenkersatz.pdf",
                    "page_count": 152,
                },
                "validity_information": {
                    "guideline_creation_date": "2025-04-01T00:00:00",
                    "valid": False,
                    "extended_validity": False,
                    "validity_range": 5,
                },
            },
        },
    )
