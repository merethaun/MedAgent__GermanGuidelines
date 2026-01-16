from typing import Dict, Any, Tuple

from app.services.system.components import render_template
from app.services.system.components.structure.decision.abstract_decision_component import AbstractDecisionComponent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class IfElseDecision(AbstractDecisionComponent, variant_name="if_else"):
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.decision_template = self.parameters.get("decision", "")
    
    def decide(self, data: Dict[str, Any]) -> Tuple[str, Any]:
        decision_basis = render_template(self.decision_template, data)
        next_component_id = self.parameters["component_a"] if decision_basis else self.parameters["component_b"]
        
        return next_component_id, decision_basis
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "decision": {
                "type": "any",
                "description": "Decide path: if True: choose next component A; else: choose next component B",
            },
            "component_a": {
                "type": "str",
                "description": "Component A ID",
            },
            "component_b": {
                "type": "str",
                "description": "Component B ID",
            },
        }
