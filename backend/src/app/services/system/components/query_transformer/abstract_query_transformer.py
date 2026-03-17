from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type

from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent


class AbstractQueryTransformer(AbstractComponent, variant_name="query_transformer"):
    variants: Dict[str, Type["AbstractQueryTransformer"]] = {}
    
    default_parameters: Dict[str, Any] = {
        "query": "{start.current_user_input}",
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: Optional[str] = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractQueryTransformer.variants[variant_name] = cls
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "query": {
                "type": "string",
                "description": "Query template resolved against workflow data.",
                "default": "{start.current_user_input}",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "query_transformer.query": {
                "type": "string",
                "description": "Resolved input query before transformation.",
            },
            "query_transformer.queries": {
                "type": "list",
                "description": "List of transformed query outputs.",
            },
            "query_transformer.primary_query": {
                "type": "string",
                "description": "Primary transformed query, usually the first entry in queries.",
            },
            "query_transformer.joined_query": {
                "type": "string",
                "description": "Space-joined representation of transformed queries.",
            },
        }
    
    @staticmethod
    def _normalize_queries(raw_queries: Any) -> List[str]:
        if raw_queries is None:
            return []
        if isinstance(raw_queries, str):
            return [raw_queries.strip()] if raw_queries.strip() else []
        
        normalized: List[str] = []
        for item in raw_queries:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    
    def _build_common_outputs(self, query: str, queries: Any) -> Dict[str, Any]:
        normalized_queries = self._normalize_queries(queries)
        primary_query = normalized_queries[0] if normalized_queries else query
        joined_query = " ".join(normalized_queries) if normalized_queries else query
        return {
            "query": query,
            "queries": normalized_queries,
            "primary_query": primary_query,
            "joined_query": joined_query,
        }
    
    @abstractmethod
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        raise NotImplementedError
