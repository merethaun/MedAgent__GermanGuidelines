from pydantic import BaseModel, ConfigDict, Field

from app.models.tools.guideline_expander import GuidelineExpanderSettings, HierarchySelectionMode, NeighborhoodDirection

NeighborhoodReferenceExpanderSettings = GuidelineExpanderSettings
HierarchyReferenceExpanderSettings = GuidelineExpanderSettings


class GraphReferenceExpanderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_name: str = Field(..., description="Logical Neo4j graph name to query.")
    limit: int = Field(default=12, ge=1, le=200, description="Maximum number of expanded references to return.")
    include_seed_references: bool = Field(default=True, description="Keep the provided seed references in the final result.")
    neighbor_depth: int = Field(default=1, ge=0, le=10, description="How many PREV/NEXT hops are considered around each seed.")
    include_section_references: bool = Field(default=True, description="Whether references from the same section as a seed should be added.")
    section_max_children: int = Field(default=24, ge=1, le=500, description="Soft cap when section-based expansion fans out strongly.")
    include_keyword_matches: bool = Field(
        default=False,
        description="Whether keyword-linked references should be considered during expansion. Usually best enabled only when keywords are curated.",
    )
    keyword_overlap_min: int = Field(
        default=2,
        ge=1,
        le=20,
        description="Minimum number of shared keywords required for keyword-based expansion when enabled.",
    )
    keyword_overlap_ratio_min: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Normalized keyword-overlap threshold based on the smaller keyword set. Enables full-coverage matches even for small keyword lists.",
    )
    include_similarity_matches: bool = Field(
        default=True,
        description="Whether SIMILAR graph edges should be used during expansion when they are present.",
    )
    similarity_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum similarity-edge score required for similarity-based expansion.",
    )

__all__ = [
    "GuidelineExpanderSettings",
    "NeighborhoodReferenceExpanderSettings",
    "HierarchyReferenceExpanderSettings",
    "GraphReferenceExpanderSettings",
    "NeighborhoodDirection",
    "HierarchySelectionMode",
]
