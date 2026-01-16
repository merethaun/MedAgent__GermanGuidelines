from copy import deepcopy
from typing import Dict, Any

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components.complex_pattern.question_decomposition.decompose_merge import MergeComponent
from app.services.system.components.generator import AbstractGenerator  # only for param merging types
from app.services.system.components.generator.ollama import OllamaGenerator


class DecomposeMergeOllamaGenerator(MergeComponent, variant_name="ollama"):
    ollama_defaults = deepcopy(OllamaGenerator.default_parameters)
    decompose_merge_defaults = deepcopy(MergeComponent.default_parameters)
    pure_generator_defaults = deepcopy(AbstractGenerator.default_parameters)
    for key in pure_generator_defaults:
        ollama_defaults.pop(key, None)
    
    default_parameters: Dict[str, Any] = {**ollama_defaults, **decompose_merge_defaults}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        # Delegate actual LLM call to the existing Azure generator
        self.generator = OllamaGenerator(component_id, name, parameters, variant)
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        self.generator.load_execution_result(result)
    
    def generate_response(self, prompt: str) -> str:
        return self.generator.generate_response(prompt)
    
    def get_model_info(self) -> Dict[str, Any]:
        return self.generator.get_model_info()
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_decompose_merge = deepcopy(MergeComponent.get_init_parameters())
        base_ollama = deepcopy(OllamaGenerator.get_init_parameters())
        base_pure_generator = deepcopy(AbstractGenerator.get_init_parameters())
        for key in base_pure_generator:
            base_ollama.pop(key, None)
        
        merged = {**base_ollama, **base_decompose_merge}
        return merged
