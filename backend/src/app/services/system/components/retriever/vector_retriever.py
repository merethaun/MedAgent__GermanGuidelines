import time
from typing import Any, Dict, List, Optional, Tuple

from app.models.knowledge.guideline.guideline_reference import GuidelineReference, REFERENCE_TYPE_MAP
from app.models.knowledge.vector import WeaviateSearchRequest
from app.models.system.workflow_retriever import (
    MultiQueryVectorRetrieverSettings,
    VectorRetrieverSettings,
)
from app.services.service_registry import get_guideline_reference_service, get_weaviate_vector_store_service
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


def _deserialize_reference_payload(payload: Dict[str, Any]) -> GuidelineReference:
    reference_type = payload.get("type")
    model_cls = REFERENCE_TYPE_MAP.get(reference_type)
    if model_cls is None:
        raise ValueError(f"Unknown reference type in Weaviate payload: {reference_type}")
    return model_cls.model_validate(payload)


def _map_hit_to_reference(
        *,
        hit: Any,
        contained_reference_property: Optional[str],
        reference_id_property: str,
) -> Optional[GuidelineReference]:
    properties = hit.properties or {}
    if contained_reference_property:
        payload = properties.get(contained_reference_property)
        if isinstance(payload, dict):
            return _deserialize_reference_payload(payload)

    reference_id = properties.get(reference_id_property)
    if reference_id is None:
        return None

    return get_guideline_reference_service().get_reference_by_id(reference_id)


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
    
    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[List[GuidelineReference], float]:
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
        
        references: List[GuidelineReference] = []
        for hit in response.hits:
            reference = _map_hit_to_reference(
                hit=hit,
                contained_reference_property=settings.contained_reference_property,
                reference_id_property=settings.reference_id_property,
            )
            if reference is None:
                logger.debug(
                    "Skipping Weaviate hit %s because it lacks '%s' and no embedded reference payload was configured.",
                    hit.uuid,
                    settings.reference_id_property,
                )
                continue

            references.append(reference)
        
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
                "description": "Merged GuidelineReference list from all configured queries.",
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
    def _dedupe_key(result: GuidelineReference) -> str:
        if getattr(result, "id", None) is not None:
            return f"reference:{result.id}"
        return f"guideline:{result.guideline_id}|type:{result.type.value}|text:{result.extract_content()}"

    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[List[GuidelineReference], float]:
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
                    result = _map_hit_to_reference(
                        hit=hit,
                        contained_reference_property=settings.contained_reference_property,
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
