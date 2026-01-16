from copy import deepcopy
from typing import Dict, Any, Tuple

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.services.system.components.resolve_component_path import resolve_component_path
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ListComponent(AbstractComponent, variant_name="list"):
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id=component_id, name=name, parameters=parameters, variant=variant)
        
        self.next_component_id = None
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        pass
    
    def _replace_list_value_in_template(self, template, list_value: str):
        """
        Recursively replace all occurrences of `<list_value>` in the template with the actual value.
        """
        if isinstance(template, str):
            return template.replace("<list_value>", str(list_value))
        elif isinstance(template, dict):
            return {key: self._replace_list_value_in_template(value, list_value) for key, value in template.items()}
        elif isinstance(template, list):
            return [self._replace_list_value_in_template(item, list_value) for item in template]
        else:
            return template
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        Execute the component for each value in the list and collect results.
        """
        logger.info(f"Executing ListComponent with id: {self.id}")
        
        list_values = self.parameters.get("list", [])
        if type(list_values) == str:
            list_values = render_template(list_values, data)
        component_template = self.parameters.get("component_template", {})
        
        if not list_values:
            logger.error("ListComponent requires a non-empty 'list' parameter.")
            raise ValueError("ListComponent requires a non-empty 'list' parameter.")
        
        logger.debug(f"List values: {list_values}")
        
        # Store results
        components = []
        component_outputs = []
        
        for list_value in list_values:
            logger.debug(f"Processing list value: {list_value}")
            template_with_values = self._replace_list_value_in_template(component_template, list_value)
            components.append(template_with_values)
            
            # logger.debug(f"Rendering component: {template_with_values}")
            
            component_id = template_with_values["component_id"]
            name = template_with_values["name"]
            parameters = template_with_values["parameters"]
            component_path = template_with_values["type"].split("/")
            variant_cls = resolve_component_path(component_path)
            component_instance = variant_cls(component_id, name, parameters, variant=component_path[-1])
            
            # Execute the component and store the result
            data_names = data.keys()
            if any(data_name.startswith(component_id) for data_name in data_names):
                logger.warning(f"Component inside list will potentially overwrite data from id {component_id}")
            update_data, _ = component_instance.execute(data)
            data.update(update_data)
            
            relevant_keys = deepcopy({key: value for key, value in data.items() if key.startswith(f"{component_id}.")})
            result_of_component = {
                key[len(component_id) + 1:]: value for key, value in relevant_keys.items()
            }
            
            logger.debug(f"Result for component {component_id}: {result_of_component}")
            component_outputs.append(result_of_component)
        
        logger.debug(f"Component outputs: {component_outputs}")
        # Store all the component outputs under the list's id
        data[f"{self.id}.rendered_components"] = components
        data[f"{self.id}.component_outputs"] = component_outputs
        logger.info(f"Execution complete for ListComponent with id: {self.id}")
        
        return data, self.next_component_id
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        logger.debug(f"Fetching init parameters for ListComponent.")
        return {
            "list": {
                "type": "list",
                "description": "A list of values to be applied to the component template.",
            },
            "component_template": {
                "type": "dict",
                "description": "The template for each component, to be applied to each value in the list.",
            },
        }
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        logger.debug(f"Fetching output specification for ListComponent.")
        return {
            "list_generators.rendered_components": {
                "type": "list",
                "description": "A list of components executed based on list of values and component template.",
            },
            "list_generators.component_outputs": {
                "type": "list",
                "description": "A list of outputs from all generated components based on the list of values.",
            },
        }
