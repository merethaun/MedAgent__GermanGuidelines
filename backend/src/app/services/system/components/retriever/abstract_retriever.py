from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type

from app.models.system.system_chat_interaction import RetrievalResult, WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


class AbstractRetriever(AbstractComponent, variant_name="retriever"):
    variants: Dict[str, Type["AbstractRetriever"]] = {}

    def __init__(
            self,
            component_id: str,
            name: str,
            parameters: Optional[Dict[str, Any]] = None,
            variant: Optional[str] = None,
    ):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        self._last_execution_result: Optional[WorkflowComponentExecutionResult] = None

    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        self._last_execution_result = result

    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractRetriever.variants[variant_name] = cls

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "query": {
                "type": "string",
                "description": "Query template resolved against workflow data before retrieval.",
            },
        }

    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "retriever.references": {
                "type": "array",
                "description": "List of RetrievalResult objects returned by the retriever.",
            },
        }

    @abstractmethod
    def retrieve(self, query: str, data: Dict[str, Any]) -> Tuple[List[RetrievalResult], float]:
        pass

    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        try:
            query_template = self.parameters.get("query", "")
            query = render_template(query_template, data)

            logger.info("[Retriever] Executing %s (id=%s) with query=%r", self.__class__.__name__, self.id, query)
            if query.strip():
                references, latency = self.retrieve(query=query, data=data)
            else:
                references, latency = [], 0.0

            data[f"{self.id}.references"] = references
            data[f"{self.id}.latency"] = latency
            logger.info("[Retriever] %s returned %d references in %.2fs", self.id, len(references), latency)
            return data, self.next_component_id or ""
        except Exception as e:
            logger.exception("[Retriever] Execution failed for %s (id=%s)", self.__class__.__name__, self.id)
            raise RuntimeError(f"Retriever execution failed: {e}") from e
