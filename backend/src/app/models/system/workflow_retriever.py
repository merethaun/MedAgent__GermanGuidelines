from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.constants.weaviate_constants import (
    WEAVIATE_PROP_GUIDELINE_ID,
    WEAVIATE_PROP_REFERENCE_ID,
    WEAVIATE_PROP_TEXT,
)
from app.models.knowledge.vector import EmbeddingProviderSettings, WeaviateSearchMode


class VectorRetrieverSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    weaviate_collection: str = Field(..., description="Weaviate collection used for search.")
    vector_name: str = Field(default=WEAVIATE_PROP_TEXT, description="Named vector to search against.")
    limit: int = Field(default=5, ge=1, le=100, description="Maximum number of references to return.")
    mode: WeaviateSearchMode = Field(default=WeaviateSearchMode.VECTOR, description="Vector or hybrid retrieval mode.")
    keyword_properties: List[str] = Field(
        default_factory=list,
        description="BM25 properties used for hybrid search.",
    )
    alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Hybrid weighting between keyword and vector search.",
    )
    minimum_score: Optional[float] = Field(
        default=None,
        description="Optional lower bound for result score.",
    )
    provider_settings: List[EmbeddingProviderSettings] = Field(
        default_factory=list,
        description="Optional request-scoped embedding provider overrides.",
    )
    content_property: str = Field(
        default=WEAVIATE_PROP_TEXT,
        description="Hit property used as the retrieval text if no dedicated source text is configured.",
    )
    source_id_property: str = Field(
        default=WEAVIATE_PROP_GUIDELINE_ID,
        description="Hit property mapped to RetrievalResult.source_id when present.",
    )
    reference_id_property: str = Field(
        default=WEAVIATE_PROP_REFERENCE_ID,
        description="Hit property mapped to RetrievalResult.reference_id when present.",
    )
    contained_reference_property: Optional[str] = Field(
        default=None,
        description="Optional hit property containing the full serialized GuidelineReference payload.",
    )


class MultiQueryVectorQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    query: str = Field(..., description="Query template resolved against workflow data.")
    vector_name: str = Field(default=WEAVIATE_PROP_TEXT, description="Named vector used for this query.")
    weight: float = Field(default=1.0, gt=0.0, description="Relative contribution of this query to the merged ranking.")
    mode: WeaviateSearchMode = Field(
        default=WeaviateSearchMode.VECTOR,
        description="Vector or hybrid retrieval mode for this query.",
    )
    keyword_properties: List[str] = Field(
        default_factory=list,
        description="BM25 properties for this query when mode='hybrid'.",
    )
    alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Hybrid weighting between keyword and vector signals for this query.",
    )


class MultiQueryVectorRetrieverSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    weaviate_collection: str = Field(..., description="Weaviate collection used for search.")
    queries: List[MultiQueryVectorQuery] = Field(
        ...,
        min_length=1,
        description="Weighted list of query/vector combinations to execute and merge.",
    )
    limit: int = Field(default=5, ge=1, le=100, description="Maximum number of merged references to return.")
    per_query_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of hits fetched for each individual query before merging.",
    )
    minimum_score: Optional[float] = Field(
        default=None,
        description="Optional lower bound for per-query hit score when Weaviate returns scores.",
    )
    provider_settings: List[EmbeddingProviderSettings] = Field(
        default_factory=list,
        description="Optional request-scoped embedding provider overrides.",
    )
    content_property: str = Field(
        default=WEAVIATE_PROP_TEXT,
        description="Hit property used as the retrieval text.",
    )
    source_id_property: str = Field(
        default=WEAVIATE_PROP_GUIDELINE_ID,
        description="Hit property mapped to RetrievalResult.source_id when present.",
    )
    reference_id_property: str = Field(
        default=WEAVIATE_PROP_REFERENCE_ID,
        description="Hit property mapped to RetrievalResult.reference_id when present.",
    )
    contained_reference_property: Optional[str] = Field(
        default=None,
        description="Optional hit property containing the full serialized GuidelineReference payload.",
    )
