from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple, Type

from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent


class AbstractFilter(AbstractComponent, variant_name="filter"):
    variants: Dict[str, Type["AbstractFilter"]] = {}

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
            AbstractFilter.variants[variant_name] = cls

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "references_key": {
                "type": "string",
                "description": "Workflow data key or template resolving to the GuidelineReference list to filter.",
            },
            "filter_input": {
                "type": "string",
                "description": "Template resolving to the query, response, or other filter input.",
            },
            "settings": {
                "type": "object",
                "description": "Method-specific filter settings.",
            },
        }

    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "filter.references": {
                "type": "array",
                "description": "Filtered GuidelineReference list.",
            },
            "filter.decisions": {
                "type": "array",
                "description": "Per-item keep/drop decisions and scores.",
            },
        }

    @abstractmethod
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        pass
