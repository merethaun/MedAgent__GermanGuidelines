from copy import deepcopy
from typing import Dict, Any

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components.complex_pattern.question_decomposition.decompose_split import SplitComponent
from app.services.system.components.generator import AbstractGenerator  # only for param merging types
from app.services.system.components.generator.azure_open_ai import AzureOpenAIGenerator


class DecomposeSplitAzureOpenAIGenerator(SplitComponent, variant_name="azure_open_ai"):
    azure_defaults = deepcopy(AzureOpenAIGenerator.default_parameters)
    decompose_split_defaults = deepcopy(SplitComponent.default_parameters)
    pure_generator_defaults = deepcopy(AbstractGenerator.default_parameters)
    for key in pure_generator_defaults:
        azure_defaults.pop(key, None)
    
    default_parameters: Dict[str, Any] = {**azure_defaults, **decompose_split_defaults}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        # Delegate actual LLM call to the existing Azure generator
        self.generator = AzureOpenAIGenerator(component_id, name, parameters, variant)
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        self.generator.load_execution_result(result)
    
    def generate_response(self, prompt: str) -> str:
        return self.generator.generate_response(prompt)
    
    def get_model_info(self) -> Dict[str, Any]:
        return self.generator.get_model_info()
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_decompose_split = deepcopy(SplitComponent.get_init_parameters())
        base_azure = deepcopy(AzureOpenAIGenerator.get_init_parameters())
        base_pure_generator = deepcopy(AbstractGenerator.get_init_parameters())
        for key in base_pure_generator:
            base_azure.pop(key, None)
        
        merged = {**base_azure, **base_decompose_split}
        return merged
