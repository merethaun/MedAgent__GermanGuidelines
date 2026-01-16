from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchResult, WeaviateSearchChunkResult


class ScoreInput(BaseModel):
    name: str
    type: str
    description: str


class SimilarityScore(BaseModel):
    name: str
    description: str
    inputs: List[ScoreInput]


class RerankRequest(BaseModel, extra="allow"):
    query: str
    original_search_result: WeaviateSearchResult


class FilterTopNThresholdRequest(BaseModel):
    original_search_result: WeaviateSearchResult
    top_n: Optional[int] = Field(default=None, ge=1)
    threshold: Optional[float] = None  # your service enforces "at least one set"


class DeduplicateRequest(BaseModel, extra="allow"):
    original_search_result: WeaviateSearchResult
    keep_all_guidelines: bool = True
    compared_property: str = "text"
    cutoff_similarity: float = Field(default=0.95, ge=0.0, le=1.0)


class AutomergeRequest(BaseModel, extra="allow"):
    original_search_result: List[WeaviateSearchChunkResult]
    simple_ratio_threshold: float = 0.6
