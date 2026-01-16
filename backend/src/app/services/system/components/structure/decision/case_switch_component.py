from typing import Dict, Any, Tuple

from app.services.system.components import render_template
from app.services.system.components.structure.decision.abstract_decision_component import AbstractDecisionComponent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class CaseDecision(AbstractDecisionComponent, variant_name="case"):
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        cases = self.parameters.get("cases", {})
        cases = sorted(cases, key=lambda x: x["order"])
        self.cases_with_templates = [
            (case["condition"], case["chosen_component"])
            for case in cases
        ]
    
    def decide(self, data: Dict[str, Any]) -> Tuple[str, Any]:
        executed_conditions = []
        
        for condition_template, component_id in self.cases_with_templates:
            condition = render_template(condition_template, data)
            executed_conditions.append(condition)
            if condition:
                data[f"{self.id}.condition_executions"] = executed_conditions
                data[f"{self.id}.next_component"] = component_id
                return component_id, executed_conditions
        
        raise ValueError(f"No case matched for {self.id}: {executed_conditions}")
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "cases": {
                "type": "list",
                "description": "List of (order, condition, chosen_component)",
                "example": [
                    {"order": 0, "condition": "True", "chosen_component": "component_a"},
                    {"order": 1, "condition": "False", "chosen_component": "component_b"},
                ],
            },
        }
