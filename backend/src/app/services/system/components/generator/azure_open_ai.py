import os
from typing import Dict, Any

from openai import AzureOpenAI, OpenAI

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components.generator import AbstractGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AzureOpenAIGenerator(AbstractGenerator, variant_name="azure_open_ai"):
    default_parameters: Dict[str, Any] = {
        **AbstractGenerator.default_parameters,
        "api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
        "api_base": os.getenv("AZURE_OPENAI_API_BASE", ""),
        "api_type": os.getenv("AZURE_OPENAI_API_TYPE", None),
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-07-18"),
        "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1"),
        "temperature": float(os.getenv("AZURE_OPENAI_TEMPERATURE", 0.7)),
        "max_tokens": int(os.getenv("AZURE_OPENAI_MAX_TOKENS", 256)),
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.api_type = parameters.get("api_type") or self.default_parameters.get("api_type")
        api_key = parameters.get("api_key") or self.default_parameters.get("api_key")
        
        if self.api_type == "azure":
            api_version = parameters.get("api_version") or self.default_parameters.get("api_version")
            api_base = parameters.get("api_base") or self.default_parameters.get("api_base")
            
            self.client = OpenAI(api_key=api_key, base_url=api_base)
        else:
            self.client = OpenAI(api_key=api_key)
        self.chat_history = []
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        prompt = result.output.get(f"{self.id}.prompt")
        response = result.output.get(f"{self.id}.response")
        self.chat_history.append(
            {
                "role": "user", "content": prompt,
            },
        )
        self.chat_history.append(
            {
                "role": "assistant", "content": response,
            },
        )
    
    def generate_response(self, prompt: str) -> str:
        # logger.debug(f"[AzureOpenAIGenerator] Prompt:\n{prompt}")
        self.chat_history.append(
            {
                "role": "user", "content": prompt,
            },
        )
        try:
            temperature = float(self.parameters["temperature"])
            max_tokens = int(self.parameters["max_tokens"])
            if self.parameters["deployment_name"] in ["o3", "gpt-5"]:
                response = self.client.chat.completions.create(
                    model=self.parameters["deployment_name"],
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=max_tokens,
                )
            else:
                response = self.client.chat.completions.create(
                    model=self.parameters["deployment_name"],
                    messages=self.chat_history,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            response_text = response.choices[0].message.content
        except Exception as e:
            logger.error(f"[AzureOpenAIGenerator] Failed to generate response: {e}", exc_info=True)
            raise RuntimeError(f"AzureOpenAIGenerator encountered an issue: {e}.")
        
        self.chat_history.append(
            {
                "role": "assistant", "content": response_text,
            },
        )
        
        return response_text
    
    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "Azure OpenAI",
            "deployment": self.parameters["deployment_name"],
            "version": self.parameters["api_version"],
        }
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "api_key": {
                    "type": "string",
                    "description": "Azure OpenAI API key",
                },
                "api_base": {
                    "type": "string",
                    "description": "Azure OpenAI API base URL",
                },
                "api_type": {
                    "type": "string",
                    "description": "API type (usually 'azure')",
                },
                "api_version": {
                    "type": "string",
                    "description": "API version used by Azure OpenAI",
                },
                "deployment_name": {
                    "type": "string",
                    "description": "Azure OpenAI deployment name",
                },
                "temperature": {
                    "type": "float",
                    "description": "Controls randomness in output (0.0 - 1.0)",
                },
                "max_tokens": {
                    "type": "int",
                    "description": "Maximum number of tokens to generate",
                },
            },
        )
        return base_params
