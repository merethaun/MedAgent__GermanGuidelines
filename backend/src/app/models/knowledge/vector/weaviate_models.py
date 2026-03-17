from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.common.py_object_id import PyObjectId
from .embedding_models import EmbeddingProviderSettings, VectorizerDescriptor

SUPPORTED_WEAVIATE_PROPERTY_DATA_TYPES = {
    "text",
    "text[]",
    "int",
    "int[]",
    "number",
    "number[]",
    "boolean",
    "boolean[]",
    "date",
    "date[]",
    "uuid",
    "uuid[]",
    "geocoordinates",
    "blob",
    "phonenumber",
    "object",
    "object[]",
}


class WeaviateSearchMode(str, Enum):
    VECTOR = "vector"
    HYBRID = "hybrid"


class VectorCollectionMappedField(str, Enum):
    REFERENCE_TYPE = "reference_type"
    HEADERS = "headers"
    GUIDELINE_TITLE = "guideline_title"
    GUIDELINE_KEYWORDS = "guideline_keywords"
    REFERENCE_KEYWORDS = "reference_keywords"


class MetadataContentMode(str, Enum):
    DEFAULT = "default"
    SKIP_HEADING_METADATA = "skip_heading_metadata"


class WeaviateCollectionProperty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., description="Property name stored in the Weaviate object.")
    data_type: str = Field(..., description="Weaviate data type, for example 'text', 'int', or 'number'.")
    description: Optional[str] = Field(default=None, description="Short property description for schema docs.")
    
    @field_validator("data_type", mode="before")
    @classmethod
    def _normalize_and_validate_data_type(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("data_type must be a string")
        
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_WEAVIATE_PROPERTY_DATA_TYPES:
            raise ValueError(
                "Unsupported Weaviate property data_type. "
                f"Supported values: {', '.join(sorted(SUPPORTED_WEAVIATE_PROPERTY_DATA_TYPES))}",
            )
        return normalized


class WeaviateNamedVector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., description="Weaviate named vector name.")
    source_property: str = Field(..., description="Property whose text content is embedded for this vector.")
    provider: str = Field(..., description="Registered embedding provider used to produce this named vector.")
    distance_metric: str = Field(default="cosine", description="Weaviate distance metric for this named vector.")
    description: Optional[str] = Field(default=None, description="Short purpose of this vector.")


class VectorCollectionIngestionMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    content_property: str = Field(
        default="text",
        description="Collection property that receives the extracted reference content.",
    )
    mapped_properties: Dict[str, VectorCollectionMappedField] = Field(
        default={},
        description="Additional collection properties filled from derived reference/guideline metadata.",
    )
    metadata_content_mode: MetadataContentMode = Field(
        default=MetadataContentMode.SKIP_HEADING_METADATA,
        description="How metadata references should be converted into content text.",
    )
    skip_references_without_content: bool = Field(
        default=True,
        description="If true, references with empty derived content are skipped during ingestion.",
    )


class CreateWeaviateCollectionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
                "reference_group_id": "69b2b1ea9ced93a73a11bcde",
                "description": "Reference-group linked collection for chunked guideline references.",
                "properties": [
                    {"name": "text", "data_type": "text", "description": "Mapped reference content"},
                    {"name": "chunk_index", "data_type": "int", "description": "Insertion order inside this collection"},
                    {"name": "guideline_id", "data_type": "text", "description": "Mongo guideline id"},
                    {"name": "reference_id", "data_type": "text", "description": "Mongo reference id"},
                    {"name": "reference_type", "data_type": "text", "description": "Reference type"},
                    {"name": "headers", "data_type": "text", "description": "Joined hierarchy path"},
                    {"name": "guideline_title", "data_type": "text", "description": "Register number plus guideline title"},
                    {"name": "guideline_keywords", "data_type": "text", "description": "Joined guideline-level keywords and context"},
                    {"name": "reference_keywords", "data_type": "text", "description": "Joined reference-level keywords"},
                ],
                "named_vectors": [
                    {
                        "name": "text",
                        "source_property": "text",
                        "provider": "baai-bge-m3",
                        "distance_metric": "manhattan",
                        "description": "Main embedding over mapped reference content",
                    },
                    {
                        "name": "headers",
                        "source_property": "headers",
                        "provider": "baai-bge-m3",
                        "distance_metric": "manhattan",
                        "description": "Embedding over hierarchy headers",
                    },
                ],
                "ingestion_mapping": {
                    "content_property": "text",
                    "mapped_properties": {
                        "reference_type": "reference_type",
                        "headers": "headers",
                        "guideline_title": "guideline_title",
                        "guideline_keywords": "guideline_keywords",
                        "reference_keywords": "reference_keywords",
                    },
                    "metadata_content_mode": "skip_heading_metadata",
                    "skip_references_without_content": True,
                },
            },
        },
    )
    
    name: str = Field(..., description="Collection name. Must start with an uppercase letter in Weaviate.")
    reference_group_id: PyObjectId = Field(
        ...,
        description="Guideline reference group this vector collection is linked to.",
    )
    description: str = Field(default="", description="Human-readable collection description.")
    properties: List[WeaviateCollectionProperty] = Field(..., min_length=1)
    named_vectors: List[WeaviateNamedVector] = Field(..., min_length=1)
    ingestion_mapping: VectorCollectionIngestionMapping = Field(
        default=VectorCollectionIngestionMapping(),
        description="Mapping used when ingesting all references from the linked reference group into this collection.",
    )
    
    @model_validator(mode="after")
    def _validate_named_vectors(self) -> "CreateWeaviateCollectionRequest":
        property_names = {entry.name for entry in self.properties}
        for vector in self.named_vectors:
            if vector.source_property not in property_names:
                raise ValueError(
                    f"named vector '{vector.name}' references unknown source_property '{vector.source_property}'",
                )
        if self.ingestion_mapping.content_property not in property_names:
            raise ValueError(
                f"ingestion content_property '{self.ingestion_mapping.content_property}' must exist in properties",
            )
        for property_name in self.ingestion_mapping.mapped_properties:
            if property_name not in property_names:
                raise ValueError(
                    f"mapped ingestion property '{property_name}' must exist in properties",
                )
        return self


class WeaviateCollectionResponse(CreateWeaviateCollectionRequest):
    pass


class WeaviateUpsertObjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    properties: Dict[str, Any] = Field(..., description="Object payload stored in Weaviate.")
    provider_settings: List[EmbeddingProviderSettings] = Field(
        default=[],
        description="Request-scoped embedding provider configuration used to build named vectors.",
    )
    
    @field_validator("properties")
    @classmethod
    def _ensure_properties(cls, properties: Dict[str, Any]) -> Dict[str, Any]:
        if not properties:
            raise ValueError("properties must not be empty")
        return properties


class WeaviateObjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    uuid: str
    properties: Dict[str, Any]


class WeaviateSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    query: str = Field(..., description="Text query that will be embedded before search.")
    vector_name: str = Field(..., description="Named vector to search against.")
    provider_settings: List[EmbeddingProviderSettings] = Field(
        default=[],
        description="Request-scoped embedding provider configuration used to embed the query.",
    )
    limit: int = Field(default=5, ge=1, le=100, description="Maximum number of hits to return.")
    mode: WeaviateSearchMode = Field(default=WeaviateSearchMode.VECTOR)
    keyword_properties: List[str] = Field(
        default=[],
        description="Properties used for BM25 when mode='hybrid'. Leave empty for pure vector search.",
    )
    alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Hybrid weighting between keyword and vector search. Only used in hybrid mode.",
    )
    minimum_score: Optional[float] = Field(
        default=None,
        description="Drop hits below this score when Weaviate returns scores.",
    )
    
    @field_validator("query")
    @classmethod
    def _validate_query(cls, query: str) -> str:
        if not query.strip():
            raise ValueError("query must not be empty")
        return query


class WeaviateSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    uuid: str
    score: Optional[float] = None
    distance: Optional[float] = None
    properties: Dict[str, Any]


class WeaviateSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    collection_name: str
    vector_name: str
    mode: WeaviateSearchMode
    hits: List[WeaviateSearchHit]


class IngestReferenceGroupRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "guideline_id": "69b2b1ea9ced93a73a11bcdf",
                "provider_settings": [
                    {
                        "provider": "baai-bge-m3",
                        "model_name": "BAAI/bge-m3",
                        "batch_size": 8,
                    },
                ],
                "continue_on_error": False,
            },
        },
    )
    
    guideline_id: Optional[str] = Field(
        default=None,
        description="Optional guideline id. If provided, only that guideline is replaced in the collection; otherwise the full linked reference group is ingested.",
    )
    provider_settings: List[EmbeddingProviderSettings] = Field(
        default=[],
        description="Request-scoped embedding provider configuration used while vectorizing inserted reference content.",
    )
    continue_on_error: bool = Field(
        default=False,
        description="If true, continue processing later references after one insertion fails.",
    )


class IngestReferenceGroupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    collection_name: str
    reference_group_id: PyObjectId
    inserted_object_count: int
    skipped_reference_ids: List[str]
    failed_reference_ids: List[str]


class IngestGuidelineRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "provider_settings": [
                    {
                        "provider": "baai-bge-m3",
                        "model_name": "BAAI/bge-m3",
                        "batch_size": 8,
                    },
                ],
            },
        },
    )
    
    provider_settings: List[EmbeddingProviderSettings] = Field(
        default=[],
        description="Request-scoped embedding provider configuration used while vectorizing this guideline's references.",
    )


class DeleteGuidelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    collection_name: str
    guideline_id: str
    deleted_object_count: int


class WeaviateCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    distance_metrics: List[str]
    vectorizers: List[VectorizerDescriptor]
