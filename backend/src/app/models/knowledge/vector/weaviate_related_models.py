from typing import Optional, List, Dict, Union

from pydantic import BaseModel, Field
from weaviate.collections.classes.config import DataType


class WeaviateVectorizer(BaseModel):
    name: str
    embedder: str
    vectorizer_property: str = Field(
        default="text", description="The property of the collection which will be used to create the vector.",
    )
    relevance_factor: int = Field(
        default=1, description="The factor with which this retriever counts into calculation of score upon search.",
    )
    distance_metric: str = Field(
        default="cosine",
        description="The metric used to calculate distance. For options, take a look here: https://docs.weaviate.io/weaviate/config-refs/distances",
    )


class WeaviateProperty(BaseModel):
    name: str
    data_type: DataType
    description: Optional[str] = Field(default=None)


class WeaviateCollection(BaseModel):
    collection_name: str = Field(description="Name of the weaviate collection, must be UNIQUE per weaviate database")
    description: Optional[str] = Field(default="A weaviate collection")
    vectorizers: List[WeaviateVectorizer] = Field(description="The vectorizers used to create the vectors for indices / search")
    properties: List[WeaviateProperty] = Field(
        default=[
            WeaviateProperty(name="text", data_type=DataType.TEXT, description="Text of the guideline"),
            WeaviateProperty(
                name="reference_id", data_type=DataType.TEXT, description="MongoDB reference ID",
            ),
            WeaviateProperty(
                name="guideline_id", data_type=DataType.TEXT, description="MongoDB guideline ID",
            ),
            WeaviateProperty(
                name="chunk_index", data_type=DataType.INT, description="Index of the chunk in the original text",
            ),
        ],
        description="The properties of the collection; !!Be aware that updating this can hinder the functionality "
                    "of the database interaction (e.g., problems with creating reference id, ...!!",
    )


class WeaviateSearchChunkResult(BaseModel, extra="allow"):
    retrieved_chunk: dict = Field(description="Retrieved chunk object with properties as defined for collection")
    score: float = Field(description="Score of the retrieved chunk")


class WeaviateSearchResult(BaseModel):
    results: List[WeaviateSearchChunkResult]
    duration: float = Field(description="Duration of the search in seconds")


class WeaviateSingleSearchProperties(BaseModel):
    query: str = Field(description="Query string to search for")
    top_k: int = Field(description="Number of top results to retrieve")
    distance_threshold: Optional[float] = Field(default=None, description="Maximum allowed (normalized) distance")
    score_threshold: Optional[float] = Field(default=None, description="Minimum required (normalized) score")
    overwrite_vectorizer_manual_weights: Optional[Dict[str, Union[float, int]]] = Field(
        default=None,
        description="Alternative manual weights for vectorizers (!! need to be configured in order to work; use name: target_weight dictionary!!)",
    )
    bm25_search_properties: Optional[List[str]] = Field(
        default=None, description="Properties to be used for BM25 search (if using hybrid search)",
    )
    alpha: Optional[float] = Field(
        default=None, description="Alpha value utilized for hybrid search (if using hybrid search)",
    )


class QueryWithSearchContribution(BaseModel):
    query: str = Field(description="Query string to search for")
    query_weight: float = Field(description="Weight of the query")
    vectorizer_name: str = Field(
        description="Name of the vectorizer to use -> to apply multiple vectorizers to one query, put an additional query contribution",
    )


class WeaviateMultiSearchProperties(BaseModel):
    queries: List[QueryWithSearchContribution] = Field(description="Queries with assigned vectorizer and search contribution")
    top_k: int = Field(description="Number of top results to retrieve")
    distance_threshold: Optional[float] = Field(default=None, description="Maximum allowed (normalized) distance")
    score_threshold: Optional[float] = Field(default=None, description="Minimum required (normalized) score")
    bm25_query: Optional[str] = Field(default=None, description="BM25 query string to search for")
    bm25_search_properties: Optional[List[str]] = Field(
        default=None, description="Properties to be used for BM25 search (if using hybrid search)",
    )
    alpha: Optional[float] = Field(
        default=None, description="Alpha value utilized for hybrid search (if using hybrid search)",
    )
