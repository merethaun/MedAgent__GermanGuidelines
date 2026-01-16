from copy import deepcopy
from typing import Dict, Any, Tuple, List, Optional

from app.models.knowledge.vector.weaviate_related_models import QueryWithSearchContribution
from app.services.system.components import render_template
from app.services.system.components.retriever import AbstractRetriever
from app.utils.logger import setup_logger
from app.utils.service_creators import get_vector_db_service

logger = setup_logger(__name__)


class MultiQueriesVectorRetriever(AbstractRetriever, variant_name="multi_queries_vector_retriever"):
    
    @staticmethod
    def _build_query_contribution_objects(queries: List[dict]) -> List[QueryWithSearchContribution]:
        result = []
        for qdict in queries:
            result.append(
                QueryWithSearchContribution(query=qdict["query"], query_weight=qdict["query_weight"], vectorizer_name=qdict["vectorizer_name"]),
            )
        return result
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.weaviate_vector_service = get_vector_db_service()
        
        self.weaviate_collection = self.parameters["weaviate_collection"]
        self.distance_threshold = self.parameters.get("distance_threshold", None)
        self.score_threshold = self.parameters.get("score_threshold", None)
        
        # List of dicts -> List[QueryWithSearchContribution]
        query_contributions_raw = self.parameters["queries"]
        if isinstance(query_contributions_raw, str):
            self.query_contributions = query_contributions_raw
        else:
            self.query_contributions = self._build_query_contribution_objects(query_contributions_raw)
        
        self.bm25_query = self.parameters.get("bm25_query", None)
        if self.bm25_query:
            self.bm25_search_properties = self.parameters.get("bm25_search_properties", [])
            self.alpha = self.parameters.get("alpha", 1.0)
        else:
            self.bm25_search_properties = []
            self.alpha = 1.0
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.pop("query", None)
        base_params.update(
            {
                "queries": {
                    "type": "list",
                    "description": "List of queries, each with associated vectorizers and relevance factors",
                },
                "top_k": {
                    "type": "int",
                    "description": "Number of top results to retrieve (default 5)",
                },
                "weaviate_collection": {
                    "type": "string",
                    "description": "Name of the Weaviate collection to query",
                },
                "distance_threshold": {
                    "type": "float",
                    "description": "OPTIONAL: can set maximum allowed distance (not directly linked to score!! But this sets a filter on the configured distance)",
                },
                "score_threshold": {
                    "type": "float",
                    "description": "OPTIONAL: set minimum score required (SCORE is normalized!!)",
                },
                "bm25_query": {
                    "type": "string",
                    "description": "Term based on which the 'most relevant' entries are extracted (will be resolved with the variables specified)",
                },
                "bm25_search_properties": {
                    "type": "list",
                    "description": "OPTIONAL properties to apply bm25 to (then requires also a provided alpha)",
                    "default": [],
                },
                "alpha": {
                    "type": "float",
                    "description": "OPTIONAL: Hybrid search weighting between BM25 (0.0) and vector search (1.0)",
                    "default": 1.0,
                },
            },
        )
        return base_params
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "multi_queries_vector_retriever.queries": {
                "type": "list", "description": "List of queries used for retrieval, available under namespace of component",
            },
            "multi_queries_vector_retriever.bm25_query": {
                "type": "string", "description": "The bm25-query used for retrieval, available under namespace of component",
            },
            "multi_queries_vector_retriever.results": {
                "type": "list", "description": "List of retrieved objects with retrieval scores",
            },
        }
    
    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[list, float]:
        pass
    
    def retrieve_multi(self, queries: list, bm25_query: Optional[str], data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
        logger.info(f"[MultiRetriever] Performing multi-query retrieval on collection '{self.weaviate_collection}'")
        top_k = render_template(self.parameters.get("top_k", 5), data)
        
        response = self.weaviate_vector_service.multi_query_search(
            collection_name=self.weaviate_collection,
            queries=queries,
            top_k=top_k,
            distance_threshold=self.distance_threshold,
            score_threshold=self.score_threshold,
            bm25_query=bm25_query,
            bm25_search_properties=self.bm25_search_properties,
            alpha=self.alpha,
        ).model_dump()
        
        results = response.get("results", [])
        latency = float(response.get("duration", 0.0))
        logger.debug(f"[MultiRetriever] Retrieved {len(results)} results in {latency:.2f} s")
        return results, latency
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            logger.info(f"[MultiRetriever] Starting execution for {self.__class__.__name__} (ID: {self.id})")
            
            if isinstance(self.query_contributions, str):
                query_contributions = render_template(self.query_contributions, data)
                formatted_query_contributions = self._build_query_contribution_objects(query_contributions)
            else:
                query_contributions = deepcopy(self.query_contributions)
                for qwc in query_contributions:
                    query_template = qwc.query
                    query = render_template(query_template, data)
                    qwc.query = query
                formatted_query_contributions = query_contributions
            
            if self.bm25_query is not None:
                bm25_query_template = self.bm25_query
                bm25_query = render_template(bm25_query_template, data)
            else:
                bm25_query = None
            
            formatted_query_contributions = [
                q for q in formatted_query_contributions if q.query.strip()
            ]
            
            logger.info(f"[MultiRetriever] Queries: {len(formatted_query_contributions)}")
            data[f"{self.id}.queries"] = formatted_query_contributions
            data[f"{self.id}.bm25_query"] = bm25_query
            
            if not formatted_query_contributions and (not bm25_query or not bm25_query.strip()):
                results, latency = [], 0.0
            else:
                results, latency = self.retrieve_multi(queries=formatted_query_contributions, bm25_query=bm25_query, data=data)
            logger.info(f"[MultiRetriever] Retrieved {len(results) if results else 0} results in {latency:.2f} s")
            
            data[f"{self.id}.results"] = results
            data[f"{self.id}.latency"] = latency
            logger.info(f"[MultiRetriever] Execution completed successfully")
            return data, self.next_component_id
        
        except Exception as e:
            logger.exception(f"[MultiRetriever] Failed to retrieve for {self.__class__.__name__} (ID: {self.id}):")
            logger.error(f"[MultiRetriever] Error details: {str(e)}")
            raise RuntimeError(f"Retriever execution failed: {e}")
