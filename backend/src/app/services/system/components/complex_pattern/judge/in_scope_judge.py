import os
from typing import Dict, Any, List

from app.services.system.components.complex_pattern.judge.abstract_judge import AbstractJudge
from app.utils.llama_index.llm_interaction import OllamaLlamaIndexLLM, AzureOpenAILlamaIndexLLM
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

INSIDE_SCOPE_PROMPT = """Decide if the QUESTION is answerable based on the described KNOWLEDGE SOURCE, and is within the SCOPE of the system.

SCOPE:
{scope_block}

KNOWLEDGE SOURCE:
{knowledge_block}

RULES:
- Return 1 only if the question clearly falls under the knowledge source coverage and is withing scope.
- Return 0 otherwise (including ambiguity).

IN SCOPE examples (→ 1):
{few_shot_positive_examples}

OUT OF SCOPE examples (→ 0):
{few_shot_negative_examples}

OUTPUT:
Return exactly one character: 1 or 0. No explanation.

INPUT QUESTION:
{question}
"""


class QuestionInScopeJudge(AbstractJudge, variant_name="in_scope"):
    default_parameters: Dict[str, Any] = {
        **AbstractJudge.default_parameters,
        "generator_backend": "azure",  # "azure" | "ollama"
        # Azure LLM config
        "azure_api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
        "azure_api_base": os.getenv("AZURE_OPENAI_API_BASE", ""),
        "azure_api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        "azure_chat_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1"),
        "azure_temperature": 0.7,
        "azure_max_tokens": 512,
        # Ollama LLM config
        "ollama_api_base": os.getenv("WARHOL_OLLAMA_API_BASE", "http://localhost:11434"),
        "ollama_model": "llama3.3:70b",
        "ollama_temperature": 0.7,
        "ollama_max_tokens": 512,
        # Scope definition and configuration
        "scope": "Question-answering system for expert clinicians on topics of Oral and Maxillofacial Surgery (OMFS/MKG) or similar related topics",
        "knowledge_source_description": "Official AWMF Oral and Maxillofacial Surgery (OMFS/MKG) guidelines",
        "few_shot_positive_examples": [
            "Welche Symptome können im Zusammenhang mit Weisheitszähne vorkommen?",
            "Welche Verfahren sind bei der Diagnostik einer aktiven sowie einer chronische-rheumatischen Kiefergelenkarthritis angezeigt?",
            "Welche Unterform der kindlichen Gelenkrheuma-Erkrankung ist wahrscheinlich, wenn ein siebenjähriger Junge das HLA-B27-Merkmal im Blut zeigt und gleichzeitig eine akute Regenbogenhautentzündung des Auges auftritt?",
        ],
        "few_shot_negative_examples": [
            "In welchem Jahr fiel die Berliner Mauer?",
            "Welches neue Medikament wird seit 2025 zur Behandlung von Alzheimer in Deutschland eingesetzt?",
            "Zu welchem Rheumatologen muss ich gehen?",
        ],
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.llm = None
        
        p: Dict = {**self.default_parameters, **(parameters or {})}
        
        backend = (p.get("generator_backend") or "azure").lower()
        if backend == "azure":
            
            self.llm = AzureOpenAILlamaIndexLLM(
                api_key=p["azure_api_key"],
                api_base=p["azure_api_base"],
                deployment_name=p["azure_chat_deployment"],
                api_version=p["azure_api_version"],
                temperature=float(p["azure_temperature"]),
                max_tokens=int(p["azure_max_tokens"]),
            )
        elif backend == "ollama":
            self.llm = OllamaLlamaIndexLLM(
                model=p["ollama_model"],
                api_base=p["ollama_api_base"],
                temperature=float(p["ollama_temperature"]),
                max_tokens=int(p["ollama_max_tokens"]),
            )
        else:
            raise ValueError(f"Unsupported generator_backend: {backend}")
        
        self.config = {
            "scope": p["scope"],
            "knowledge_source_description": p["knowledge_source_description"],
            "few_shot_positive_examples": p["few_shot_positive_examples"],
            "few_shot_negative_examples": p["few_shot_negative_examples"],
        }
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        
        ragas_params = {
            "generator_backend": {
                "type": "string",
                "description": "LLM backend to use.",
                "enum": ["azure", "ollama"],
                "default": "azure",
            },
            "scope": {
                "type": "string",
                "description": "Scope definition and configuration.",
                "default": "clinical QA system, OMS",
            },
            "knowledge_source_description": {
                "type": "string",
                "description": "Knowledge source description.",
                "default": "OMS guidelines",
            },
            "few_shot_positive_examples": {
                "type": "list",
                "description": "Few-shot positive examples.",
                "default": "couple of example from dataset",
            },
            "few_shot_negative_examples": {
                "type": "list",
                "description": "Few-shot negative examples.",
                "default": "couple of example from dataset",
            },
        }
        
        gen_azure_params = {
            "azure_api_key": {"type": "string", "description": "Azure OpenAI API key."},
            "azure_api_base": {"type": "string", "description": "Azure OpenAI endpoint, e.g., https://<resource>.openai.azure.com"},
            "azure_api_version": {"type": "string", "description": "Azure OpenAI API version.", "default": "2024-06-01"},
            "azure_chat_deployment": {"type": "string", "description": "Azure chat deployment name."},
            "azure_temperature": {"type": "number", "description": "Sampling temperature.", "default": 0.7},
            "azure_max_tokens": {"type": "integer", "description": "Max tokens (completion).", "default": 512},
        }
        
        gen_ollama_params = {
            "ollama_api_base": {"type": "string", "description": "Ollama base URL.", "default": "http://localhost:11434"},
            "ollama_model": {"type": "string", "description": "Ollama model name.", "default": "deepseek-r1:7b"},
            "ollama_temperature": {"type": "number", "description": "Sampling temperature.", "default": 0.7},
            "ollama_max_tokens": {"type": "integer", "description": "Num tokens to predict.", "default": 512},
            
        }
        
        return {**base_params, **ragas_params, **gen_azure_params, **gen_ollama_params}
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_output_spec()
        base_params.update(
            {
                "in_scope.question_in_scope": {"type": "bool", "description": "Either in scope or not."},
            },
        )
        return base_params
    
    @staticmethod
    def _build_prompt(
            scope: str, knowledge_source_description: str, few_shot_positive_examples: List[str], few_shot_negative_examples: List[str],
            question: str,
    ) -> str:
        p_ex_block = "\n".join(f"- {p_ex}" for p_ex in few_shot_positive_examples) if few_shot_positive_examples else "/"
        n_ex_block = "\n".join(f"- {n_ex}" for n_ex in few_shot_negative_examples) if few_shot_negative_examples else "/"
        return INSIDE_SCOPE_PROMPT.format(
            scope_block=scope,
            knowledge_block=knowledge_source_description,
            few_shot_positive_examples=p_ex_block,
            few_shot_negative_examples=n_ex_block,
            question=question,
        )
    
    @staticmethod
    def _call_llm(llm, prompt: str):
        try:
            llm_response = llm.complete(prompt)  # returns a string
        except AttributeError:
            llm_response = llm.predict(prompt)
        
        if not isinstance(llm_response, str):
            llm_text = getattr(llm_response, "text", "")
        else:
            llm_text = llm_response
        return llm_text
    
    def judge(self, query: str, _, __, data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"{self.id}: Starting evaluation")
        
        prompt = self._build_prompt(
            self.config["scope"], self.config["knowledge_source_description"], self.config["few_shot_positive_examples"],
            self.config["few_shot_negative_examples"], query,
        )
        
        response = self._call_llm(self.llm, prompt)
        question_in_scope = response.strip().lower() == "1"
        data[f"{self.id}.question_in_scope"] = question_in_scope
        logger.info(f"{self.id}: Evaluation complete -> {'question in scope' if question_in_scope else 'question out of scope'}")
        
        return data
