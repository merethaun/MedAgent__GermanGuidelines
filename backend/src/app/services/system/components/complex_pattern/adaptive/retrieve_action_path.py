from typing import Dict, Any, Tuple, List

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult, QueryWithSearchContribution
from app.services.knowledge.guidelines.keywords.keyword_service import KeywordService
from app.services.knowledge.vector import WeaviateVectorDBService, AdvancedDBService
from app.services.system.components import AbstractComponent, render_template
from app.services.system.components.post_processor.context_retriever import add_context
from app.utils.logger import setup_logger
from app.utils.service_creators import get_keyword_service, get_vector_db_service, get_advanced_db_service

logger = setup_logger(__name__)


class RetrieveActionComponent(AbstractComponent, variant_name="retrieve_action_path"):
    default_parameters: Dict[str, Any] = {
        "top_k": 10,
        "context_augment_c": 0.5,
        "bm25_properties": ["text", "headers", "reference_keywords"],
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        
        self.next_component_id = None
        
        self.queries_temp = parameters["queries"]
        self.top_k_temp = parameters.get("top_k") or self.default_parameters["top_k"]
        self.relevance_filter = 0.4
        self.context_augment_c = parameters.get("context_augment_c") or self.default_parameters["context_augment_c"]
        self.weaviate_collection = parameters["weaviate_collection"]
        self.bm25_properties = parameters.get("bm25_properties") or self.default_parameters["bm25_properties"]
        
        self.keywords_service: KeywordService = get_keyword_service()
        self.weaviate_vector_service: WeaviateVectorDBService = get_vector_db_service()
        self.advanced_vector_service: AdvancedDBService = get_advanced_db_service()
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "queries": {
                "type": "str",
                "description": "Template for how to get to queries (list of strings).",
            },
            "top_k": {
                "type": "int",
                "description": "Template for how to get to top_k setting.",
                "default": 10,
            },
            "context_augment_c": {
                "type": "float",
                "description": "Template for how to get to context size.",
                "default": 0.5,
            },
            "weaviate_collection": {
                "type": "string",
                "description": "Name of the Weaviate collection to query",
            },
            "bm25_properties": {
                "type": "List[str]",
                "description": "Properties to use for BM25 search",
            },
        }
    
    def rerank_and_filter(self, query: str, retrievals, relevance_filter: float = 0.4):
        ordered_retrievals = self.advanced_vector_service.rerank(
            query=query,
            retrieved_chunks=retrievals,
            reranking_option="llm",
            compared_property="text",
            model="gpt-4.1",
        )
        logger.debug(f"Reranked results")
        
        filtered_retrieval = self.advanced_vector_service.filter_top_n_and_threshold(
            retrieved_chunks=ordered_retrievals,
            threshold=relevance_filter,
        )
        logger.debug(f"Filtered results to {len(filtered_retrieval)} results (remove {len(ordered_retrievals) - len(filtered_retrieval)})")
        return filtered_retrieval
    
    def run_query(self, query: str, top_k: int = 10, relevance_filter: float = 0.4, context_augment_c: float = 0.5):
        logger.debug(f"Running query: {query[:100]}...")
        
        keywords = self.keywords_service.extract_llm(
            text=query,
            model="gpt-5",
            temperature=0.7,
            max_tokens=2048,
            scope_description="German guidelines for Oral and Maxillofacial surgery from the AWMF.",
            guidance_additions=[
                "Prefer multi-word medical terms, diagnoses, procedures, imaging, therapies, risk factors, patient groups, and staging systems.",
                "Keep names that are relevant to characterize the text.",
            ],
            ignore_terms=["Tabelle", "Abbildung", "Leitlinie"],
            important_terms=[
                "kann bestehen", "besteht", "indiziert", "Indikation", "kann", "sollte", "keine", "nicht", "soll", "können", "sollten", "notwendig",
                "empfehlenswert", "empfehlen", "sollten",
            ],
            examples=[
                {
                    "text": "Welche Symptome können im Zusammenhang mit Weisheitszähne vorkommen?",
                    "keywords": ["Symptome", "können", "Weisheitszähne"],
                },
            ],
            min_keywords=1,
            max_keywords=25,
        )
        logger.debug(f"Extracted {len(keywords)} keywords")
        
        queries = [QueryWithSearchContribution(query=query, query_weight=1, vectorizer_name="text")]
        if keywords:
            queries.append(QueryWithSearchContribution(query=" ".join(keywords), query_weight=1, vectorizer_name="headers"))
        
        retrieval = self.weaviate_vector_service.multi_query_search(
            collection_name=self.weaviate_collection,
            queries=queries,
            top_k=top_k,
            distance_threshold=1.0,
            score_threshold=0.0,
            bm25_query=" ".join(keywords) if keywords else None,
            bm25_search_properties=self.bm25_properties,
            alpha=0.7,
        ).results
        logger.debug(f"Retrieved {len(retrieval)} results")
        
        filtered_retrieval = self.rerank_and_filter(retrievals=retrieval, query=query, relevance_filter=relevance_filter)
        
        context_augment = add_context(
            filtered_retrieval, [], context_augment_c, self.weaviate_vector_service, self.weaviate_collection,
        )
        logger.debug(f"Added context to {len(context_augment)} results (insert {len(filtered_retrieval) - len(context_augment)})")
        
        filtered_retrieval = self.rerank_and_filter(retrievals=context_augment, relevance_filter=relevance_filter, query=query)
        
        return filtered_retrieval
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        queries = render_template(self.queries_temp, data)
        top_k = render_template(self.top_k_temp, data)
        context_augment_c = render_template(self.context_augment_c, data)
        
        seen_ref = []
        final_retrieval = []
        for q in queries:
            query_retrieval = self.run_query(q, top_k=top_k, relevance_filter=self.relevance_filter, context_augment_c=context_augment_c)
            for ar in query_retrieval:
                if ar.retrieved_chunk["reference_id"] not in seen_ref:
                    seen_ref.append(ar.retrieved_chunk["reference_id"])
                    final_retrieval.append(ar)
        logger.debug(f"Final retrieval size: {len(final_retrieval)}")
        data[f"{self.id}.retrievals"] = final_retrieval
        
        return data, self.next_component_id
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "retrieve_action_path.retrievals": {
                "type": List[WeaviateSearchChunkResult],
                "description": "Tracks the action with their settings + results (in form of scores) -> can track progress",
            },
        }
