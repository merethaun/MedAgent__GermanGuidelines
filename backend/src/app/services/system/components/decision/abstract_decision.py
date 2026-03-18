from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple, Type

from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent


class AbstractDecisionComponent(AbstractComponent, variant_name="decision"):
    variants: Dict[str, Type["AbstractDecisionComponent"]] = {}

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
            AbstractDecisionComponent.variants[variant_name] = cls

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {}

    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "decision.value": {
                "type": "Any",
                "description": "Resolved decision value, often a boolean or case label.",
            },
            "decision.label": {
                "type": "string",
                "description": "Normalized string label for downstream branching.",
            },
            "decision.reason": {
                "type": "string",
                "description": "Short explanation for why the decision was produced.",
            },
        }

    def _write_outputs(self, data: Dict[str, Any], *, value: Any, label: str, reason: str = "") -> Dict[str, Any]:
        data[f"{self.id}.value"] = value
        data[f"{self.id}.label"] = label
        data[f"{self.id}.reason"] = reason
        return data

    @abstractmethod
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        raise NotImplementedError
