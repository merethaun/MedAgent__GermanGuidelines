from abc import abstractmethod, ABC
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Union, List, Optional, Tuple

from pydantic import BaseModel, Field, ConfigDict, field_serializer, field_validator

from app.models.common.py_object_id import PyObjectId


# ---- Options for reference types ----
class ReferenceType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    RECOMMENDATION = "recommendation"
    STATEMENT = "statement"
    METADATA = "metadata"


# ---- Shared structures ----

class GuidelineReferenceGroup(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    name: str = Field(description="Name of the reference group", examples=["question_dataset", "system_1"])


class GuidelineHierarchyEntry(BaseModel):
    title: str = Field(description="This hierarchy level's title (e.g., section header)")
    heading_level: int = Field(description="Depth of the heading (0=root, 1=chapter, 2=section, ...)")
    heading_number: str = Field(description="Heading number such as '4.2.1'")
    order: int = Field(default=0, description="Order of the heading in the document")
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_by_name=True,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "title": "",
                    "heading_level": 0,
                    "heading_number": "",
                    "order": 0,
                },
                {
                    "title": "Introduction",
                    "heading_level": 1,
                    "heading_number": "1",
                    "order": 0,
                },
                {
                    "title": "Background",
                    "heading_level": 2,
                    "heading_number": "2.2",
                    "order": 1,
                },
            ],
        },
    )


class BoundingBox(BaseModel):
    page: int = Field(description="Page number of the bounding box")
    positions: Tuple[float, float, float, float] = Field(
        description="x0, y0, x1, y1 coordinates of the bounding box",
    )
    
    @field_validator("positions", mode="before")
    @classmethod
    def coerce_positions(cls, v):
        if isinstance(v, list) and len(v) == 4:
            return tuple(v)
        return v
    
    @field_serializer("positions")
    def serialize_positions(self, positions):
        return list(positions)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


class GuidelineDocumentHierarchyEntry(BaseModel):
    hierarchy_entry: GuidelineHierarchyEntry = Field(
        description="Document structure from root to this hierarchy instance",
    )
    positions: List[BoundingBox] = Field(
        description="Bounding boxes of the hierarchy instance (all possible positions of 'belonging' text)",
    )
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


class GuidelineDocumentHierarchy(BaseModel):
    guideline_id: PyObjectId = Field(description="MongoDB ID of the referenced guideline")
    document_hierarchy: List[GuidelineDocumentHierarchyEntry] = Field(
        description="All structures (headings) in hierarchy for entire document",
    )
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )


class GuidelineReferenceBase(BaseModel, ABC):
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="MongoDB document ID")
    reference_group_id: Optional[PyObjectId] = Field(
        default=None, description="MongoDB ID of the guideline group this reference belongs to",
    )
    guideline_id: PyObjectId = Field(description="MongoDB ID of the referenced guideline")
    type: ReferenceType = Field(description="Discriminator field that defines the reference type")
    bboxs: List[BoundingBox] = Field(
        default=[], description="Bounding boxes of the reference (all possible positions of 'belonging' text)",
    )
    document_hierarchy: List[GuidelineHierarchyEntry] = Field(
        default=[], description="Document structure from root to this reference",
    )
    note: Optional[str] = Field(default=None, description="Additional notes or comments about the reference")
    created_automatically: bool = Field(
        default=True, description="True if extracted automatically; changes to False after editing",
    )
    created_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the reference was created or updated",
    )
    associated_keywords: Optional[List[str]] = Field(
        default=None, description="Keywords extracted from the contained reference (normalized to selected terms for keywords)",
    )
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )
    
    @abstractmethod
    def extract_content(self) -> str:
        raise NotImplementedError
    
    @abstractmethod
    def update_content(self, new_content: str) -> None:
        raise NotImplementedError


# ---- Concrete Reference Types ----

class GuidelineTextReference(GuidelineReferenceBase):
    type: Literal[ReferenceType.TEXT] = Field(
        default=ReferenceType.TEXT, description="Reference type identifier for text references",
    )
    contained_text: str = Field(
        description="The actual text content extracted from the document",
        examples=[
            "Der Begriff der Retention bezeichnet eine Position des Weisheitszahnes, bei der nach Abschluss des "
            "Wurzelwachstums die Okklusionsebene nicht erreicht wird.",
        ],
    )
    
    def extract_content(self) -> str:
        return self.contained_text
    
    def update_content(self, new_content: str) -> None:
        self.contained_text = new_content
        self.created_automatically = False
        self.created_date = datetime.now(timezone.utc)


class GuidelineImageReference(GuidelineReferenceBase):
    type: Literal[ReferenceType.IMAGE] = Field(
        default=ReferenceType.IMAGE, description="Reference type identifier for image references",
    )
    caption: str = Field(
        default="", description="Caption text associated with the image", examples=["Image 1: ..."],
    )
    describing_text: Optional[str] = Field(default=None, description="Additional text describing the image (optional)")
    
    def extract_content(self) -> str:
        return (f"{self.caption}: " if self.caption else "") + self.describing_text or ""
    
    def update_content(self, new_content: str) -> None:
        self.caption = new_content
        self.created_automatically = False
        self.created_date = datetime.now(timezone.utc)


class GuidelineTableReference(GuidelineReferenceBase):
    type: Literal[ReferenceType.TABLE] = Field(
        default=ReferenceType.TABLE, description="Reference type identifier for table references",
    )
    caption: str = Field(default="", description="Optional table caption or label")
    plain_text: str = Field(default="", description="Plain text content extracted from the table")
    table_markdown: str = Field(default="", description="Markdown representation of the table content")
    
    def extract_content(self) -> str:
        return (f"{self.caption}: " if self.caption else "") + self.table_markdown or self.plain_text or ""
    
    def update_content(self, new_content: str) -> None:
        self.plain_text = new_content
        self.table_markdown = new_content
        self.created_automatically = False
        self.created_date = datetime.now(timezone.utc)


class GuidelineRecommendationReference(GuidelineReferenceBase):
    type: Literal[ReferenceType.RECOMMENDATION] = Field(
        default=ReferenceType.RECOMMENDATION, description="Reference type identifier for recommendations",
    )
    recommendation_title: Optional[str] = Field(
        default=None, description="Optional heading or identifier of the recommendation", examples=["Empfehlung"],
    )
    recommendation_content: str = Field(
        description="Main textual content of the recommendation",
        examples=["Eine dreidimensionale Bildgebung (beispielsweise DVT/CT) kann indiziert sein ..."],
    )
    recommendation_grade: str = Field(
        description="Consensus or strength level of the recommendation (e.g., A, B, 0)",
        examples=["Starker Konsens (4/4, zwei Enthaltungen aufgrund eines Interessenskonfliktes)"],
    )
    
    def extract_content(self) -> str:
        return f"{self.recommendation_title}: " + self.recommendation_content + f"\n({self.recommendation_grade})"
    
    def update_content(self, new_content: str) -> None:
        self.recommendation_content = new_content
        self.created_automatically = False
        self.created_date = datetime.now(timezone.utc)


class GuidelineStatementReference(GuidelineReferenceBase):
    type: Literal[ReferenceType.STATEMENT] = Field(
        default=ReferenceType.STATEMENT,
        description="Reference type identifier for statement (similar to recommendation)",
    )
    statement_title: Optional[str] = Field(
        default=None, description="Optional heading or identifier of the statement", examples=["Statement"],
    )
    statement_content: str = Field(
        description="Main textual content of the statement",
        examples=[
            "Eine 3D-Bildgebung ist vor einer Weisheitszahnentfernung nicht erforderlich, wenn in der "
            "konventionell zweidimensionalen Bildgebung ...",
        ],
    )
    statement_consensus_grade: str = Field(
        description="Consensus or strength level of the statement",
        examples=["Starker Konsens (4/4, zwei Enthaltungen aufgrund eines Interessenskonfliktes)"],
    )
    
    def extract_content(self) -> str:
        return (f"{self.statement_title}: " if self.statement_title else "") + self.statement_content + (
            f"\n({self.statement_consensus_grade})" if self.statement_consensus_grade else "")
    
    def update_content(self, new_content: str) -> None:
        self.statement_content = new_content
        self.created_automatically = False
        self.created_date = datetime.now(timezone.utc)


class GuidelineMetadataReference(GuidelineReferenceBase):
    type: Literal[ReferenceType.METADATA] = Field(
        default=ReferenceType.METADATA, description="Reference type identifier for metadata entries",
    )
    metadata_type: str = Field(
        description="Type of metadata, such as 'title', 'authors', 'publication_date', etc.",
        examples=["validity_information"],
    )
    metadata_content: str = Field(
        description="Extracted text content of the metadata", examples=["Stand: August 2019; Gültig bis: August 2024"],
    )
    
    def extract_content(self) -> str:
        return self.metadata_content
    
    def update_content(self, new_content: str) -> None:
        self.metadata_content = new_content
        self.created_automatically = False
        self.created_date = datetime.now(timezone.utc)


# ---- Polymorphic union for API routing / responses ----
GuidelineReference = Union[
    GuidelineTextReference,
    GuidelineImageReference,
    GuidelineTableReference,
    GuidelineRecommendationReference,
    GuidelineStatementReference,
    GuidelineMetadataReference,
]

# ---- Mapping for deserialization based on type ----
REFERENCE_TYPE_MAP = {
    ReferenceType.TEXT.value: GuidelineTextReference,
    ReferenceType.IMAGE.value: GuidelineImageReference,
    ReferenceType.TABLE.value: GuidelineTableReference,
    ReferenceType.RECOMMENDATION.value: GuidelineRecommendationReference,
    ReferenceType.STATEMENT.value: GuidelineStatementReference,
    ReferenceType.METADATA.value: GuidelineMetadataReference,
}
