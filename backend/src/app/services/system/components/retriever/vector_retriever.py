from typing import Dict, Any, Tuple

from app.services.system.components import render_template
from app.services.system.components.retriever import AbstractRetriever
from app.utils.logger import setup_logger
from app.utils.service_creators import get_vector_db_service

logger = setup_logger(__name__)


class VectorRetriever(AbstractRetriever, variant_name="vector_retriever"):
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.weaviate_vector_service = get_vector_db_service()
        
        self.bm25_search_properties = self.parameters.get("bm25_search_properties", None)
        if self.bm25_search_properties and self.parameters.get("alpha", None) is None:
            raise ValueError(f"[VectorRetriever] If BM25 search is active, an alpha value is required for hybrid search")
        else:
            self.alpha = self.parameters.get("alpha", 1.0)
        
        self.distance_threshold = self.parameters.get("distance_threshold", None)
        self.score_threshold = self.parameters.get("score_threshold", None)
        
        self.overwrite_vectorizer_manual_weights = self.parameters.get("overwrite_vectorizer_manual_weights", {})
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "top_k": {
                    "type": "int",
                    "description": "Number of top results to retrieve (defaults to 5)",
                },
                "weaviate_collection": {
                    "type": "string",
                    "description": "Weaviate collection to use for the retrieval (will send query, top_k)",
                },
                "distance_threshold": {
                    "type": "float",
                    "description": "OPTIONAL: can set maximum allowed distance (not directly linked to score!! But this sets a filter on the configured distance)",
                },
                "score_threshold": {
                    "type": "float",
                    "description": "OPTIONAL: set minimum score required (SCORE is normalized!!)",
                },
                "overwrite_vectorizer_manual_weights": {
                    "type": "dict",
                    "description": "OPTIONAL: Vectorizer name + updated weight dictionary",
                },
                "bm25_search_properties": {
                    "type": "list",
                    "description": "OPTIONAL properties to apply bm25 to (then requires also a provided alpha)",
                    "default": [],
                },
                "alpha": {
                    "type": "float",
                    "description": "OPTIONAL parameter balancing BM25 search (alpha = 1) and vector search (alpha = 0)",
                    "default": 0.0,
                },
            },
        )
        return base_params
    
    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[list, float]:
        logger.debug(f"Retrieving results for query: {query}")
        
        if query.strip() == "":
            logger.warning("Empty query, returning empty results")
            return [], 0.0
        
        weaviate_collection = self.parameters.get("weaviate_collection")
        top_k = render_template(self.parameters.get("top_k", 5), data)
        
        logger.info(f"Searching collection '{weaviate_collection}' for top {top_k} results")
        response = self.weaviate_vector_service.single_query_search(
            collection_name=weaviate_collection, query=query, top_k=top_k, distance_threshold=self.distance_threshold,
            score_threshold=self.score_threshold, overwrite_vectorizer_manual_weights=self.overwrite_vectorizer_manual_weights,
            bm25_search_properties=self.bm25_search_properties, alpha=self.alpha,
        ).model_dump()
        results = response.get("results", [])
        latency = float(response.get("duration", 0.0))
        logger.debug(f"Retrieved {len(results)} results in {latency:.2f} s")
        return results, latency
