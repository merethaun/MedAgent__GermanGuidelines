from copy import deepcopy
from typing import Dict, Any

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components.generator import AbstractGenerator  # only for param merging types
from app.services.system.components.generator.ollama import OllamaGenerator
from app.services.system.components.generator.query_adjust import AbstractQueryAdjuster


class OllamaQueryAdjuster(AbstractQueryAdjuster, variant_name="ollama"):
    ollama_defaults = deepcopy(OllamaGenerator.default_parameters)
    base_query_adjust_defaults = deepcopy(AbstractQueryAdjuster.default_parameters)
    pure_generator_defaults = deepcopy(AbstractGenerator.default_parameters)
    for key in pure_generator_defaults:
        ollama_defaults.pop(key, None)
    
    default_parameters: Dict[str, Any] = {**ollama_defaults, **base_query_adjust_defaults}
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        # Delegate actual LLM call to the existing Azure generator
        self.generator = OllamaGenerator(component_id, name, parameters, variant)
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        prompt = result.output.get(f"{self.id}.prompt")
        response = result.output.get(f"{self.id}.query_adjust")
        self.generator.chat_history.append(
            {
                "role": "user", "content": prompt,
            },
        )
        self.generator.chat_history.append(
            {
                "role": "assistant", "content": response,
            },
        )
    
    def generate_response(self, prompt: str) -> str:
        return self.generator.generate_response(prompt)
    
    def get_model_info(self) -> Dict[str, Any]:
        return self.generator.get_model_info()
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_query_adjust = deepcopy(AbstractQueryAdjuster.get_init_parameters())
        base_ollama = deepcopy(OllamaGenerator.get_init_parameters())
        base_pure_generator = deepcopy(AbstractGenerator.get_init_parameters())
        for key in base_pure_generator:
            base_ollama.pop(key, None)
        
        merged = {**base_ollama, **base_query_adjust}
        return merged
