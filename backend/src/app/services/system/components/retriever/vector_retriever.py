import time
from typing import Any, Dict, List, Optional, Tuple

from app.models.knowledge.vector import WeaviateSearchRequest
from app.models.system.system_chat_interaction import RetrievalResult
from app.models.system.workflow_retriever import (
    MultiQueryVectorRetrieverSettings,
    VectorRetrieverSettings,
)
from app.services.service_registry import get_weaviate_vector_store_service
from app.services.system.components.retriever.abstract_retriever import AbstractRetriever
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


def _render_value(value: Any, data: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_template(value, data)
    if isinstance(value, dict):
        return {key: _render_value(inner_value, data) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [_render_value(item, data) for item in value]
    return value


def _map_hit_to_retrieval_result(
        *,
        hit: Any,
        content_property: str,
        source_id_property: str,
        reference_id_property: str,
) -> Optional[RetrievalResult]:
    properties = hit.properties or {}
    reference_id = properties.get(reference_id_property)
    source_id = properties.get(source_id_property)
    retrieval_text = properties.get(content_property)
    
    if reference_id is None and (source_id is None or retrieval_text is None):
        return None
    
    return RetrievalResult(
        reference_id=reference_id,
        source_id=source_id,
        retrieval=retrieval_text,
        weaviate_uuid=getattr(hit, "uuid", None),
        weaviate_score=getattr(hit, "score", None),
        weaviate_distance=getattr(hit, "distance", None),
        weaviate_properties=properties,
    )


class VectorRetriever(AbstractRetriever, variant_name="vector_retriever"):
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "settings": {
                    "type": "object",
                    "description": "VectorRetrieverSettings payload used for the Weaviate search.",
                },
            },
        )
        return base
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_output_spec()
        base.update(
            {
                "retriever.latency": {
                    "type": "float",
                    "description": "Weaviate search latency in seconds.",
                },
            },
        )
        return base
    
    def _resolve_settings(self, data: Dict[str, Any]) -> VectorRetrieverSettings:
        raw_settings = self.parameters.get("settings")
        if raw_settings is None:
            raise ValueError("VectorRetriever requires a 'settings' object.")
        rendered = _render_value(raw_settings, data)
        return VectorRetrieverSettings.model_validate(rendered)
    
    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[List[RetrievalResult], float]:
        settings = self._resolve_settings(data)
        logger.debug(
            "VectorRetriever.retrieve: component_id=%s collection=%s vector=%s mode=%s limit=%s query_chars=%d",
            self.id,
            settings.weaviate_collection,
            settings.vector_name,
            settings.mode,
            settings.limit,
            len(query),
        )
        request = WeaviateSearchRequest(
            query=query,
            vector_name=settings.vector_name,
            provider_settings=settings.provider_settings,
            limit=settings.limit,
            mode=settings.mode,
            keyword_properties=settings.keyword_properties,
            alpha=settings.alpha,
            minimum_score=settings.minimum_score,
        )
        
        started = time.time()
        response = get_weaviate_vector_store_service().search(settings.weaviate_collection, request)
        latency = time.time() - started
        
        references: List[RetrievalResult] = []
        for hit in response.hits:
            properties = hit.properties or {}
            retrieval_result = _map_hit_to_retrieval_result(
                hit=hit,
                content_property=settings.content_property,
                source_id_property=settings.source_id_property,
                reference_id_property=settings.reference_id_property,
            )
            if retrieval_result is None:
                logger.debug(
                    "Skipping Weaviate hit %s because it lacks '%s' and '%s'/'%s'.",
                    hit.uuid,
                    settings.reference_id_property,
                    settings.source_id_property,
                    settings.content_property,
                )
                continue
            
            references.append(retrieval_result)
        
        logger.info(
            "VectorRetriever succeeded: component_id=%s collection=%s vector=%s mode=%s returned=%d",
            self.id,
            settings.weaviate_collection,
            settings.vector_name,
            settings.mode,
            len(references),
        )
        return references, latency


class MultiQueriesVectorRetriever(AbstractRetriever, variant_name="multi_queries_vector_retriever"):
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "settings": {
                "type": "object",
                "description": "MultiQueryVectorRetrieverSettings payload used for weighted multi-query Weaviate search.",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "retriever.references": {
                "type": "array",
                "description": "Merged RetrievalResult list from all configured queries.",
            },
            "retriever.latency": {
                "type": "float",
                "description": "Total elapsed search latency across all executed queries.",
            },
            "retriever.queries": {
                "type": "array",
                "description": "Resolved query configurations used during execution.",
            },
        }
    
    def _resolve_settings(self, data: Dict[str, Any]) -> MultiQueryVectorRetrieverSettings:
        raw_settings = self.parameters.get("settings")
        if raw_settings is None:
            raise ValueError("MultiQueriesVectorRetriever requires a 'settings' object.")
        rendered = _render_value(raw_settings, data)
        if isinstance(rendered, dict):
            fallback_query = data.get("start.current_user_input")
            queries = rendered.get("queries")
            if fallback_query is not None and isinstance(queries, list):
                for query_config in queries:
                    if isinstance(query_config, dict) and "query" not in query_config:
                        query_config["query"] = fallback_query
        return MultiQueryVectorRetrieverSettings.model_validate(rendered)
    
    @staticmethod
    def _dedupe_key(result: RetrievalResult) -> str:
        if result.reference_id is not None:
            return f"reference:{result.reference_id}"
        return f"source:{result.source_id}|text:{result.retrieval}"
    
    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[List[RetrievalResult], float]:
        raise NotImplementedError("MultiQueriesVectorRetriever uses execute() to handle multiple queries.")
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            settings = self._resolve_settings(data)
            service = get_weaviate_vector_store_service()
            started = time.time()
            logger.debug(
                "MultiQueriesVectorRetriever.execute: component_id=%s collection=%s configured_queries=%d limit=%s per_query_limit=%s",
                self.id,
                settings.weaviate_collection,
                len(settings.queries),
                settings.limit,
                settings.per_query_limit,
            )
            
            merged_results: Dict[str, Dict[str, Any]] = {}
            resolved_queries: List[Dict[str, Any]] = []
            
            for query_config in settings.queries:
                if not query_config.query.strip():
                    continue
                logger.debug(
                    "MultiQueriesVectorRetriever sub-query: component_id=%s query=%r vector=%s weight=%s mode=%s",
                    self.id,
                    query_config.query,
                    query_config.vector_name,
                    query_config.weight,
                    query_config.mode.value,
                )
                
                resolved_queries.append(
                    {
                        "query": query_config.query,
                        "vector_name": query_config.vector_name,
                        "weight": query_config.weight,
                        "mode": query_config.mode.value,
                    },
                )
                
                request = WeaviateSearchRequest(
                    query=query_config.query,
                    vector_name=query_config.vector_name,
                    provider_settings=settings.provider_settings,
                    limit=settings.per_query_limit,
                    mode=query_config.mode,
                    keyword_properties=query_config.keyword_properties,
                    alpha=query_config.alpha,
                    minimum_score=settings.minimum_score,
                )
                response = service.search(settings.weaviate_collection, request)
                
                for rank, hit in enumerate(response.hits, start=1):
                    result = _map_hit_to_retrieval_result(
                        hit=hit,
                        content_property=settings.content_property,
                        source_id_property=settings.source_id_property,
                        reference_id_property=settings.reference_id_property,
                    )
                    if result is None:
                        continue
                    
                    score = hit.score if hit.score is not None else max(0.0, 1.0 - ((rank - 1) / max(settings.per_query_limit, 1)))
                    weighted_score = float(score) * query_config.weight
                    key = self._dedupe_key(result)
                    
                    current = merged_results.get(key)
                    if current is None:
                        merged_results[key] = {
                            "result": result,
                            "score": weighted_score,
                        }
                    else:
                        current["score"] += weighted_score
            
            ranked_results = [
                entry["result"]
                for entry in sorted(
                    merged_results.values(),
                    key=lambda entry: entry["score"],
                    reverse=True,
                )[:settings.limit]
            ]
            latency = time.time() - started
            
            data[f"{self.id}.queries"] = resolved_queries
            data[f"{self.id}.references"] = ranked_results
            data[f"{self.id}.latency"] = latency
            
            logger.info(
                "MultiQueriesVectorRetriever succeeded: component_id=%s collection=%s queries=%d returned=%d latency=%.2fs",
                self.id,
                settings.weaviate_collection,
                len(resolved_queries),
                len(ranked_results),
                latency,
            )
            return data, self.next_component_id or ""
        except Exception as e:
            logger.exception("[Retriever] Execution failed for %s (id=%s)", self.__class__.__name__, self.id)
            raise RuntimeError(f"Retriever execution failed: {e}") from e
