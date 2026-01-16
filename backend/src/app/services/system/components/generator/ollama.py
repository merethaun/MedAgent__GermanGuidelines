import os
from typing import Dict, Any

import requests

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components.generator import AbstractGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class OllamaGenerator(AbstractGenerator, variant_name="ollama"):
    default_parameters: Dict[str, Any] = {
        **AbstractGenerator.default_parameters,
        "api_base": os.getenv("WARHOL_OLLAMA_API_BASE", "http://localhost:11434"),
        "model": os.getenv("OLLAMA_MODEL_NAME", "deepseek-r1:7b"),
        "temperature": float(os.getenv("OLLAMA_TEMPERATURE", 0.7)),
        "max_tokens": int(os.getenv("OLLAMA_MAX_TOKENS", 256)),
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.api_base = parameters.get("api_base")
        self.model = parameters.get("model")
        self.temperature = parameters.get("temperature")
        self.max_tokens = parameters.get("max_tokens")
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
        import json
        
        # logger.debug(f"[OllamaGenerator] Prompt:\n{prompt}")
        self.chat_history.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": self.chat_history,
            "temperature": self.temperature,
            "options": {"num_predict": self.max_tokens},
            "stream": True,  # <-- enable streaming
            "think": False,
        }
        
        try:
            url = f"{self.api_base}/api/chat"
            logger.debug(f"Sending POST request to {url} with payload: {payload}")
            
            # stream=True and no read-timeout (connect timeout 10s, read timeout None)
            with requests.post(
                    url,
                    json=payload,
                    stream=True,
                    timeout=(60, None),
                    headers={"Accept": "application/x-ndjson"},
            ) as response:
                logger.debug(f"Response status: {response.status_code}")
                response.raise_for_status()
                
                chunks = []
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue  # skip keep-alives/blank lines
                    try:
                        part = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug(f"Ignoring non-JSON stream line: {line!r}")
                        continue
                    
                    # upstream error payloads
                    if "error" in part and part["error"]:
                        raise RuntimeError(f"Ollama upstream error: {part['error']}")
                    
                    msg = part.get("message") or {}
                    content = msg.get("content")
                    if content:
                        chunks.append(content)
                    
                    if part.get("done"):
                        break
                
                response_text = "".join(chunks).strip()
                if not response_text:
                    raise RuntimeError("OllamaGenerator received an empty streamed response.")
        
        except Exception as e:
            # Undo the user message we appended if anything failed
            self.chat_history.pop()
            logger.error(f"[OllamaGenerator] Failed to generate response: {e}", exc_info=True)
            raise RuntimeError(f"OllamaGenerator encountered an issue: {e}.")
        
        self.chat_history.append({"role": "assistant", "content": response_text})
        return response_text
    
    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "Ollama",
            "model": self.model,
            "endpoint": self.api_base,
        }
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "api_base": {
                    "type": "string",
                    "description": "Base URL of the Ollama API",
                },
                "model": {
                    "type": "string",
                    "description": "Model name used by Ollama (e.g., 'deepseek-r1:7b')",
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
