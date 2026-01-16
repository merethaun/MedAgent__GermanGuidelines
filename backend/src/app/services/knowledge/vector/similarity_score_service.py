import os
from typing import Any, List
from urllib.parse import urlparse

import numpy as np
import weaviate
from pymongo.synchronous.collection import Collection
from scipy.spatial.distance import cosine

from app.models.knowledge.vector.advanced_db_models import SimilarityScore, ScoreInput
from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult, WeaviateCollection
from app.services.knowledge.vector import VectorizerService
from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)

ALL_SIMILARITY_SCORES: List[SimilarityScore] = [
    SimilarityScore(
        name="vector_similarity",
        description="Cosine similarity between the chunk embedding and a query embedding.",
        inputs=[
            ScoreInput(name="query", type="str", description="The query string to compare against."),
            ScoreInput(
                name="property_from_chunk", type="str", description="The property of the retrieved chunk which to compare query embedding to.",
            ),
            ScoreInput(name="vectorizer", type="str", description="The vectorizer used to create embeddings."),
        ],
    ),
    # SimilarityScore(
    #     name="bm25_score",
    #     description="Keyword relevance score based on BM25 ranking from a raw query.",
    #     inputs=[
    #         {"name": "query", "type": "str", "description": "The raw query string for keyword search."}
    #     ],
    # ),
    SimilarityScore(
        name="llm_relevance",
        description="LLM-prompted score representing how relevant the chunk is to the query.",
        inputs=[
            ScoreInput(name="query", type="str", description="The query string to compare against."),
            ScoreInput(
                name="property_from_chunk", type="str", description="The property of the retrieved chunk which to compare query embedding to.",
            ),
            ScoreInput(name="llm_model", type="Optional[str]", description="Optional LLM model name or alias."),
        ],
    ),
    # SimilarityScore(
    #     name="metadata_similarity",
    #     description="Field-wise metadata comparison with a target set of values.",
    #     inputs=[
    #         {"name": "target_metadata", "type": "Dict[str, Any]", "description": "Key-value pairs to compare against chunk metadata."}
    #     ],
    # ),
    # SimilarityScore(
    #     name="property_forward",
    #     description="Extracts a numeric property or metadata field directly as score.",
    #     inputs=[
    #         {"name": "property", "type": "str", "description": "Name of the field to extract."},
    #         {"name": "source", "type": "str", "description": "'metadata' or 'chunk' (defaults to 'metadata')."}
    #     ],
    # ),
    # SimilarityScore(
    #     name="compose",
    #     description="Apply a sequence of scoring strategies (group by outer, then score inner).",
    #     inputs=[
    #         {"name": "score_chain", "type": "List[Tuple[str, Dict[str, Any]]]", "description": "List of (score_type, config_dict) pairs to apply in order."}
    #     ],
    # ),
    # SimilarityScore(
    #     name="weighted_sum",
    #     description="Calculate a weighted sum of multiple scoring strategies.",
    #     inputs=[
    #         {"name": "score_weights", "type": "Dict[str, float]", "description": "Score type to weight mapping."},
    #         {"name": "score_configs", "type": "Dict[str, Dict[str, Any]]", "description": "Score type to config mapping."}
    #     ],
    # ),
]


class SimilarityScoreService:
    """Computation of similarity score for retrieved chunk"""
    
    def __init__(self, vector_dbs_collection: Collection, vectorizer_service: VectorizerService):
        self.vectorizer_service = vectorizer_service
        self.vector_dbs_collection = vector_dbs_collection
        
        weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8081")
        parsed = urlparse(weaviate_url)
        self.client = weaviate.connect_to_custom(
            http_host=parsed.hostname, http_port=parsed.port, http_secure=parsed.scheme == "https",
            grpc_host=parsed.hostname, grpc_port=50051, grpc_secure=parsed.scheme == "https",
        )
        self.client.connect()
    
    @staticmethod
    def get_available_similarity_score_defs() -> List[SimilarityScore]:
        return ALL_SIMILARITY_SCORES
    
    @staticmethod
    def get_similarity_score_def(score_type: str) -> SimilarityScore:
        for score in ALL_SIMILARITY_SCORES:
            if score.name == score_type:
                return score
        raise ValueError(f"Unknown similarity score type: {score_type}")
    
    def calculate_similarity_order_key(
            self, retrieval_result: WeaviateSearchChunkResult, collection: WeaviateCollection, similarity_score_type: str, **kwargs,
    ) -> Any:
        score_type = self.get_similarity_score_def(similarity_score_type)
        
        if score_type.name == "vector_similarity":
            return self._vector_similarity_score(retrieval_result, collection, **kwargs)
        
        else:
            raise ValueError(f"Unknown similarity score type: {similarity_score_type}")
    
    def _vector_similarity_score(
            self, retrieval_result: WeaviateSearchChunkResult, collection: WeaviateCollection, query: str, property_from_chunk: str, vectorizer: str,
    ):
        compare_value = str(retrieval_result.retrieved_chunk[property_from_chunk])
        assert vectorizer in self.vectorizer_service.list_available_vectorizers()
        
        embs = self.vectorizer_service.vectorize(texts=[query, compare_value], provider=vectorizer)
        query_emb = np.array(embs[0])
        compare_value_emb = np.array(embs[1])
        
        similarity = 1.0 - float(cosine(query_emb, compare_value_emb))
        return similarity
