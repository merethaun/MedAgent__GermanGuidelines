from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge.guideline import GuidelineReference
from app.models.knowledge.vector import EmbeddingProviderSettings
from app.models.system.workflow_expander import GraphReferenceExpanderSettings


class GraphSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_name: str = Field(..., min_length=1, description="Logical graph identifier stored inside Neo4j.")
    reference_group_id: str = Field(..., min_length=1, description="Reference group whose references should be synced into the graph.")
    guideline_id: Optional[str] = Field(
        default=None,
        description="Optional guideline restriction. If omitted, the whole reference group is synced.",
    )
    include_keyword_edges: bool = Field(
        default=True,
        description="Create HAS_KEYWORD relations from associated_keywords when present.",
    )
    include_similarity_edges: bool = Field(
        default=True,
        description="Create SIMILAR relations between semantically close references using dense embeddings.",
    )
    similarity_provider: str = Field(
        default="baai-bge-m3",
        description="Embedding provider used to build similarity edges.",
    )
    similarity_provider_settings: Optional[EmbeddingProviderSettings] = Field(
        default=None,
        description="Optional provider-specific settings for similarity-edge embedding generation.",
    )
    similarity_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Only create similarity edges when cosine similarity is at least this threshold.",
    )
    similarity_top_k: int = Field(
        default=8,
        ge=1,
        le=100,
        description="Maximum number of outgoing similarity edges created per reference.",
    )
    similarity_text_max_chars: int = Field(
        default=4000,
        ge=128,
        le=20000,
        description="Truncation limit for the text that is embedded when building similarity edges.",
    )

    @model_validator(mode="after")
    def _validate_similarity_provider_settings(self) -> "GraphSyncRequest":
        if self.similarity_provider_settings is not None and self.similarity_provider_settings.provider != self.similarity_provider:
            raise ValueError("similarity_provider_settings.provider must match similarity_provider")
        return self


class GraphSyncResponse(BaseModel):
    graph_name: str
    reference_group_id: str
    guideline_id: Optional[str] = None
    guideline_count: int
    section_count: int
    reference_count: int
    keyword_count: int
    similarity_edge_count: int


class GraphStatusResponse(BaseModel):
    available: bool
    uri: str


class GraphSearchReason(BaseModel):
    kind: Literal["seed", "neighbor", "section", "keyword", "similarity"]
    score: float = Field(default=0.0, description="Numeric contribution of this reason to the final ranking.")
    detail: Optional[str] = Field(default=None, description="Human-readable explanation of why the reference matched.")


class GraphSearchHit(BaseModel):
    reference_id: str
    score: float
    reasons: List[GraphSearchReason] = Field(default_factory=list)
    heading_path: Optional[str] = None
    guideline_id: Optional[str] = None


class GraphRetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    references: List[GuidelineReference] = Field(..., description="Seed references used as entry points into the graph.")
    settings: GraphReferenceExpanderSettings = Field(..., description="Graph expansion settings.")


class GraphRetrieveResponse(BaseModel):
    references: List[GuidelineReference] = Field(description="Resolved guideline references returned from the graph.")
    added_references: List[GuidelineReference] = Field(description="References added by the graph beyond the provided seeds.")
    graph_hits: List[GraphSearchHit] = Field(description="Graph-level match explanations for the returned references.")
    latency: float = Field(description="Graph retrieval latency in seconds.")
