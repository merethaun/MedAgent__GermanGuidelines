from copy import deepcopy
from typing import Any, Dict, List, Tuple

from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template
from app.utils.system.resolve_component_path import resolve_component_path

logger = setup_logger(__name__)


class ListComponent(AbstractComponent, variant_name="list"):
    default_parameters: Dict[str, Any] = {
        "list": [],
        "component_template": None,
        "item_placeholder": "<list_value>",
        "index_placeholder": "<list_index>",
        "collect_key_prefix": None,
    }

    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass

    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "list": {
                "type": "list",
                "description": "List of values or a workflow template resolving to a list.",
            },
            "component_template": {
                "type": "dict",
                "description": "Component definition template executed once per list item.",
            },
            "item_placeholder": {
                "type": "string",
                "description": "Placeholder replaced with the current list item inside component_template.",
                "default": "<list_value>",
            },
            "index_placeholder": {
                "type": "string",
                "description": "Placeholder replaced with the current zero-based list index inside component_template.",
                "default": "<list_index>",
            },
            "collect_key_prefix": {
                "type": "string",
                "description": "Optional prefix to filter captured child outputs. Defaults to the child component id.",
            },
        }

    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "list.items": {
                "type": "list",
                "description": "Resolved input items executed by the list component.",
            },
            "list.rendered_components": {
                "type": "list",
                "description": "Rendered child component definitions after placeholder substitution.",
            },
            "list.component_outputs": {
                "type": "list",
                "description": "Captured outputs for each child component execution.",
            },
        }

    @staticmethod
    def _normalize_list_values(raw_values: Any) -> List[Any]:
        if raw_values is None:
            return []
        if isinstance(raw_values, list):
            return raw_values
        if isinstance(raw_values, tuple):
            return list(raw_values)
        return [raw_values]

    def _replace_template_values(self, template: Any, *, item_value: Any, item_index: int) -> Any:
        item_placeholder = str(self.parameters.get("item_placeholder", self.default_parameters["item_placeholder"]))
        index_placeholder = str(self.parameters.get("index_placeholder", self.default_parameters["index_placeholder"]))

        if isinstance(template, str):
            return template.replace(item_placeholder, str(item_value)).replace(index_placeholder, str(item_index))
        if isinstance(template, dict):
            return {
                key: self._replace_template_values(value, item_value=item_value, item_index=item_index)
                for key, value in template.items()
            }
        if isinstance(template, list):
            return [
                self._replace_template_values(item, item_value=item_value, item_index=item_index)
                for item in template
            ]
        return template

    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        raw_list = self.parameters.get("list", self.default_parameters["list"])
        resolved_list = render_template(raw_list, data) if isinstance(raw_list, str) else raw_list
        list_values = self._normalize_list_values(resolved_list)
        component_template = self.parameters.get("component_template", self.default_parameters["component_template"])
        if not component_template:
            raise ValueError("ListComponent requires a non-empty 'component_template' parameter.")
        if not list_values:
            raise ValueError("ListComponent requires a non-empty 'list' parameter.")

        rendered_components: List[Dict[str, Any]] = []
        component_outputs: List[Dict[str, Any]] = []

        for index, item_value in enumerate(list_values):
            rendered_component = self._replace_template_values(
                component_template,
                item_value=item_value,
                item_index=index,
            )
            rendered_components.append(rendered_component)

            component_path = str(rendered_component["type"]).split("/")
            variant_cls = resolve_component_path(component_path)
            child = variant_cls(
                component_id=rendered_component["component_id"],
                name=rendered_component["name"],
                parameters=rendered_component.get("parameters", {}),
                variant=component_path[-1],
            )
            if self.context is not None:
                child.bind_context(self.context)

            child_data = deepcopy(data)
            updated_child_data, _ = child.execute(child_data)

            key_prefix = self.parameters.get("collect_key_prefix") or child.id
            child_outputs = {
                key[len(f"{key_prefix}."):]: value
                for key, value in updated_child_data.items()
                if key.startswith(f"{key_prefix}.")
            }
            child_outputs["list_item"] = item_value
            child_outputs["list_index"] = index
            component_outputs.append(child_outputs)

        data[f"{self.id}.items"] = list_values
        data[f"{self.id}.rendered_components"] = rendered_components
        data[f"{self.id}.component_outputs"] = component_outputs
        logger.info(
            "ListComponent succeeded: component_id=%s items=%d child_type=%s",
            self.id,
            len(list_values),
            rendered_components[0]["type"],
        )
        return data, self.next_component_id or ""
