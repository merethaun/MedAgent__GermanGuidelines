import copy
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, Type

from app.models.system.system_chat_interaction import WorkflowComponentExecutionResult


class AbstractComponent(ABC):
    variants: Dict[str, Type['AbstractComponent']] = {}
    default_parameters: Dict[str, Any] = {}
    
    def __new__(
            cls, component_id: str, name: str, parameters: Optional[Dict[str, Any]] = None, variant: Optional[str] = None,
    ) -> 'AbstractComponent':
        if variant:
            if variant not in cls.variants:
                raise ValueError(f"Variant '{variant}' is not registered for component '{cls.__name__}'")
            subclass = cls.variants[variant]
            instance = super(AbstractComponent, subclass).__new__(subclass)
        else:
            if cls.variants:
                raise ValueError(
                    f"Component '{cls.__name__}' requires a variant. Available: {list(cls.variants.keys())}",
                )
            instance = super().__new__(cls)
        return instance
    
    def __init__(
            self, component_id: str, name: str, parameters: Optional[Dict[str, Any]] = None, variant: Optional[str] = None,
    ):
        self.id = component_id
        self.name = name
        self._variant = variant or "base"
        
        merged_params = copy.deepcopy(self.default_parameters)
        if parameters:
            merged_params.update(parameters)
        self.parameters = merged_params
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        """
        Return a dictionary describing the outputs provided by the component.
        Each key is the output name, with metadata such as type and description.
        """
        return {}
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        """
        Return a dictionary describing the parameters for the component.
        Each key is the parameter name, with metadata such as type and description.
        """
        return {}
    
    @classmethod
    def register_variant(cls, name: str, variant_cls: Type['AbstractComponent']):
        cls.variants[name] = variant_cls
    
    def __init_subclass__(cls, variant_name: Optional[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if variant_name:
            AbstractComponent.variants[variant_name] = cls
    
    @abstractmethod
    def set_next_component(self, next_component_id: str):
        pass
    
    @abstractmethod
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        """
        Update the component's state with its previous execution result.
        """
        pass
    
    @abstractmethod
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        Input: data (dictionary with all previous output from previously executed components)
        Output: data (updated with produced values) + next component (str, id)
        """
        pass
    
    def execute_with_time(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        start_time = time.time()
        updated_data, next_component_id = self.execute(data)
        data.update(updated_data)
        end_time = time.time()
        execution_time = end_time - start_time
        data[f"{self.id}.execution_time"] = execution_time
        return data, next_component_id
    
    def get_variant_name(self) -> str:
        return self._variant
