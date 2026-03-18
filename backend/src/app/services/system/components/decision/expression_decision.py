from typing import Any, Dict, Tuple

from app.services.system.components.decision.abstract_decision import AbstractDecisionComponent
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


class ExpressionDecisionComponent(AbstractDecisionComponent, variant_name="expression"):
    default_parameters: Dict[str, Any] = {
        "value": False,
        "true_label": "true",
        "false_label": "false",
        "reason": "",
    }

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "value": {
                "type": "Any",
                "description": "Template or expression resolving to the decision value.",
            },
            "true_label": {
                "type": "string",
                "description": "Label emitted when the decision resolves to boolean true.",
                "default": "true",
            },
            "false_label": {
                "type": "string",
                "description": "Label emitted when the decision resolves to boolean false.",
                "default": "false",
            },
            "reason": {
                "type": "string",
                "description": "Optional reason template stored alongside the decision.",
            },
        }

    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        raw_value = self.parameters.get("value", self.default_parameters["value"])
        value = render_template(raw_value, data) if isinstance(raw_value, str) else raw_value
        reason_template = self.parameters.get("reason", self.default_parameters["reason"])
        reason = render_template(reason_template, data) if isinstance(reason_template, str) else str(reason_template or "")

        if isinstance(value, bool):
            label = self.parameters["true_label"] if value else self.parameters["false_label"]
        else:
            label = str(value).strip()

        self._write_outputs(data, value=value, label=label, reason=reason)
        logger.info("ExpressionDecisionComponent succeeded: component_id=%s label=%s", self.id, label)
        return data, self.next_component_id or ""
