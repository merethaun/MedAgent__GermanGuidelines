from typing import Any, Dict, Tuple

from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


class DeciderComponent(AbstractComponent, variant_name="decider"):
    default_parameters: Dict[str, Any] = {
        "decision": False,
        "cases": {},
        "default_case": None,
    }

    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        self.default_next_component_id = None

    def set_next_component(self, next_component_id: str):
        if self.default_next_component_id is None:
            self.default_next_component_id = next_component_id

    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "decision": {
                "type": "Any",
                "description": "Template or expression resolving to the decision value used for branching.",
            },
            "cases": {
                "type": "dict",
                "description": "Mapping from normalized decision values to target component ids.",
            },
            "default_case": {
                "type": "string",
                "description": "Optional fallback target component id when the decision value is not in cases.",
            },
        }

    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "decider.decision": {
                "type": "Any",
                "description": "Resolved branching value.",
            },
            "decider.case_key": {
                "type": "string",
                "description": "Normalized case key used to select the branch.",
            },
            "decider.selected_next_component_id": {
                "type": "string",
                "description": "Target component id selected for the next step.",
            },
        }

    @staticmethod
    def _normalize_case_key(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value).strip().lower()

    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        raw_decision = self.parameters.get("decision", self.default_parameters["decision"])
        decision_value = render_template(raw_decision, data) if isinstance(raw_decision, str) else raw_decision
        case_key = self._normalize_case_key(decision_value)

        raw_cases = self.parameters.get("cases", self.default_parameters["cases"]) or {}
        normalized_cases = {self._normalize_case_key(key): value for key, value in raw_cases.items()}
        selected_next = normalized_cases.get(case_key)
        if selected_next is None:
            selected_next = self.parameters.get("default_case", self.default_parameters["default_case"])
        if selected_next is None:
            selected_next = self.default_next_component_id
        if selected_next is None:
            raise ValueError(f"No case configured for decision '{case_key}' in DeciderComponent '{self.id}'.")

        data[f"{self.id}.decision"] = decision_value
        data[f"{self.id}.case_key"] = case_key
        data[f"{self.id}.selected_next_component_id"] = selected_next
        logger.info("DeciderComponent succeeded: component_id=%s case=%s next=%s", self.id, case_key, selected_next)
        return data, selected_next
