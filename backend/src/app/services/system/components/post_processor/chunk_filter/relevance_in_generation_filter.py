import json
import os
import re
from typing import Dict, Any, List, Tuple

import requests
from openai import AzureOpenAI, OpenAI

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components import render_template
from app.services.system.components.post_processor.chunk_filter.abstract_chunk_filter import ChunkFilterProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FILTER_CHUNKS = """You are a careful annotator.
Your job is to decide, for each retrieval snippet, whether it was used by the given response.

# Input format
Response text: {{response_text}}
- A single string

Retrievals: {{retrievals}}
- An ordered list of strings (index starting at 0).

# What “used” means
Mark a retrieval as used (true) if the response materially depends on information found in that retrieval, including:
- direct quotes or near-verbatim overlap,
- paraphrases or summaries,
- unique facts (numbers, names, definitions, claims) that clearly come from the retrieval,
- reasoning whose key premise(s) appear in the retrieval.

Mark not used (false) if:
- the content of the retrieval does not appear (even approximately) in the response,
- the response states something incompatible with the retrieval,
- the overlap is only generic/common knowledge (too vague to attribute),
- the retrieval is background that the response does not actually reflect.

If multiple retrievals overlap and the response reflects that same content, you may mark all contributing retrievals as used.
Prefer precision: credit retrievals that provide the most specific matching details.

# How to judge
- Look for distinctive overlaps: numbers, named entities, uncommon phrases, definitions, specific steps.
- Allow paraphrases: semantic equivalence counts even if wording differs.
- Ignore boilerplate (e.g., “in conclusion”), formatting, or unrelated parts of long retrievals.
- Be conservative with generic facts unless a unique phrasing/detail ties them to a retrieval.

# Output format (JSON only)

Return only a JSON array with one object per retrieval (same order as input), each of the form:
```json
{{
  "index": <number>,
  "used": <true|false>,
  "reason": "<one-sentence justification citing the matching detail or explaining the absence>",
  "evidence_response_span": "<optional short quote from the response that triggered the decision>",
  "evidence_retrieval_span": "<optional short quote from the retrieval that aligns with the response>"
}}
```
Notes:
- Keep reason short (≤ 2 sentences).
- Include evidence when helpful; omit if truly unnecessary.
- Do not include any text outside the JSON.

{few_shot_examples}
"""

examples = [
    {
        "response": "Bei einer odontogenen Infektion ohne Ausbreitungstendenz wird laut Leitlinienkontext eine alleinige Antibiotikatherapie in der Regel nicht empfohlen. Die Standardtherapie besteht in der Entlastung der Infektion, beispielsweise durch Inzision und Drainage. Eine systemische Antibiotikatherapie ist nur im Einzelfall indiziert, etwa wenn Risikofaktoren beim Patienten vorliegen oder wenn sich aus der Inzisionswunde kein Pus entleert und somit das Risiko einer weiteren Ausbreitung besteht. In solchen Situationen kann eine Antibiotikagabe sinnvoll sein, um Komplikationen zu vermeiden. Ansonsten ist bei fehlenden allgemeinen Risikofaktoren und erfolgreicher Entlastung meist keine Antibiotikatherapie notwendig.",
        "retrievals": [
            "Eine alleinige Antibiotikatherapie ist bei einer akuten odontogenen Infektion nur in Ausnahmefällen indiziert und kann zu einer Chronifizierung der Infektion führen",
            "Eine alleinige Antibiotikatherapie ist bei einer akuten odontogenen Infektion ohne Ausbreitungstendenz nur im Einzelfall indiziert und kann zu einer Chronifizierung der Infektion führen. Eine stationäre Aufnahme kann bei einer Ausbreitungstendenz und/ oder abhängig vom Risikoprofil der Patienten bestehen. Eine physikalische Therapie in Form von kühlen des infizierten Bereichs unterstützt den Rückgang der klinischen Symptome wie z.B.: Schwellung, Kieferklemme."
            "Evidenzbasierte Empfehlung\nDie odontogene Infektion mit Ausbreitungstendenz kann für den Patienten eine lebensgefährliche Situation darstellen, in der schnell und ohne lange Verzögerungen eine chirurgische Intervention durchgeführt werden soll (Empfehlungsgrad B; LoE IV [145]). \nEine odontogene Infektion ohne Ausbreitungstendenz kann bei fehlenden allgemeinen Risikofaktoren in der Regel ambulant und ohne systemische Antibiotikatherapie behandelt werden.\nKonsensstärke: 17/17"
            "Die Einnahme von nichtsteroidalen Antiphlogistika (NSAID) oder von Glukokortikoiden zu Beginn der Infektion führt nicht zu einer gesteigerten Ausbreitungstendenz der Infektion [135]. Handelt es sich um ein Infiltrat und entleert sich kein Pus aus der Inzisionswunde, ist eine Antibiotikatherapie zur Vermeidung einer weiteren Ausbreitung sinnvoll [62]. Handelt es sich um eine lokalisierte odontogene Infektion ohne Ausbreitungstendenz und entleert sich Pus, besteht die Therapie in der Entlastung der odontogenen Infektion durch eine Inzision und eine Antibiotikatherapie ist, in Abhängigkeit vom Risikoprofil des Patienten, nicht notwendig [74, 128].",
            "Die Dauer der Antibiotikatherapie richtet sich nach der Klinik der odontogenen Infektion und den Entzündungsparametern.",
        ],
        "expected_classification": [
            {
                "index": 0,
                "used": False,
                "reason": "Too general: it lacks the 'ohne Ausbreitungstendenz' condition that the response hinges on; the response’s claim is better supported by more specific retrievals.",
                "evidence_response_span": "Bei einer odontogenen Infektion ohne Ausbreitungstendenz ... eine alleinige Antibiotikatherapie ... nicht empfohlen.",
                "evidence_retrieval_span": "Eine alleinige Antibiotikatherapie ist bei einer akuten odontogenen Infektion nur in Ausnahmefällen indiziert",
            },
            {
                "index": 1,
                "used": True,
                "reason": "Direct semantic match: states that for infections without spread, antibiotics are only indicated in individual cases.",
                "evidence_response_span": "ohne Ausbreitungstendenz ... eine alleinige Antibiotikatherapie ... nicht empfohlen",
                "evidence_retrieval_span": "ohne Ausbreitungstendenz nur im Einzelfall indiziert",
            },
            {
                "index": 2,
                "used": True,
                "reason": "Explicitly supports treating cases without spread and without general risk factors without systemic antibiotics.",
                "evidence_response_span": "bei fehlenden allgemeinen Risikofaktoren ... ohne systemische Antibiotikatherapie ...",
                "evidence_retrieval_span": "ohne Ausbreitungstendenz ... bei fehlenden allgemeinen Risikofaktoren ... ohne systemische Antibiotikatherapie",
            },
            {
                "index": 3,
                "used": True,
                "reason": "Matches the conditional logic: antibiotics if no pus drains (risk of spread), otherwise incision/drainage and usually no antibiotics depending on risk profile.",
                "evidence_response_span": "wenn sich ... kein Pus entleert ... Antibiotikagabe sinnvoll ... Entlastung ... keine Antibiotikatherapie notwendig",
                "evidence_retrieval_span": "entleert sich kein Pus ... Antibiotikatherapie ... sinnvoll ... entleert sich Pus, besteht die Therapie in der Entlastung ... Antibiotikatherapie ... nicht notwendig",
            },
            {
                "index": 4,
                "used": False,
                "reason": "Duration of therapy is not discussed in the response.",
                "evidence_response_span": "",
                "evidence_retrieval_span": "Die Dauer der Antibiotikatherapie richtet sich ...",
            },
        ],
    },
]


class LLMRelevanceFilter:
    def __init__(self, model, api_key, api_base):
        self.model = model
        self.temperature = 0.7
        self.max_tokens = 5012
        
        if model in ["gpt-5", "gpt-4.1", "o3"]:
            api_type = os.getenv("OPEN_AI_TYPE")
            api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
            
            if api_type == "azure":
                api_base = api_base or os.getenv("AZURE_OPENAI_API_BASE", "")
                api_version = "2024-08-01-preview" if model in ["gpt-5", "gpt-4.1"] else "2024-02-15-preview"
                
                self.client = OpenAI(api_key=api_key, base_url=api_base)
                self.deployment_name = "azure-gpt-5-mini" if model == "gpt-5" else ("azure-gpt-4.1" if model == "gpt-4.1" else "azure-gpt-o3-mini")
            else:
                self.client = OpenAI(api_key=api_key)
                self.deployment_name = "gpt-5" if model == "gpt-5" else ("gpt-4.1" if model == "gpt-4.1" else "o3")
            
            self.generate_response = self.generate_azure_response
        elif model == "llama3_3-70b":
            self.api_base = api_base or os.getenv("WARHOL_OLLAMA_API_BASE", "")
            self.deployment_name = "llama3.3:70b"
            
            self.generate_response = self.generate_ollama_response
        
        rendered_examples = []
        for i, example in enumerate(examples):
            response = example.get("response", "")
            retrievals = example.get("retrievals", [])
            expected = example.get("expected_classification", [])
            
            rendered_examples.append(
                "\n".join(
                    [
                        f"## Example {i}",
                        "**Response**",
                        "```text",
                        response,
                        "```",
                        "**Retrievals**",
                        "```json",
                        json.dumps(retrievals, ensure_ascii=False, indent=2),
                        "```",
                        "**Expected output**",
                        "```json",
                        json.dumps(expected, ensure_ascii=False, indent=2),
                        "```",
                    ],
                ),
            )
        
        self.system_prompt = _FILTER_CHUNKS.format(few_shot_examples="# Examples\n" + "\n".join(rendered_examples) if rendered_examples else "")
        self.chat_history = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
        ]
    
    def generate_azure_response(self, prompt: str) -> str:
        self.chat_history.append({"role": "user", "content": prompt})
        
        try:
            if self.deployment_name in ["o3", "gpt-5"]:
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=self.chat_history,
                    max_completion_tokens=self.max_tokens,
                )
            else:
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=self.chat_history,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            response_text = response.choices[0].message.content
        except Exception as e:
            logger.error(f"[AzureOpenAIGenerator] Failed to generate response: {e}", exc_info=True)
            raise RuntimeError(f"AzureOpenAIGenerator encountered an issue: {e}.")
        
        logger.debug(f"[AzureOpenAIGenerator] Response:\n{response_text}")
        self.chat_history.append({"role": "assistant", "content": response_text})
        
        return response_text
    
    def generate_ollama_response(self, prompt: str) -> str:
        self.chat_history.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.deployment_name,
            "messages": self.chat_history,
            "temperature": self.temperature,
            "options": {
                "num_predict": self.max_tokens,
            },
            "stream": False,
            "think": False,
        }
        
        try:
            url = f"{self.api_base}/api/chat"
            logger.debug(f"Sending POST request to {url} with payload: {payload}")
            
            response = requests.post(url, json=payload, timeout=120.0)
            logger.debug(f"Response status: {response.status_code}, content: {response.content}")
            
            response.raise_for_status()
            
            response_json = response.json()
            response_text = response_json["message"]["content"]
            logger.debug(f"Parsed response text: {response_text}")
        
        except requests.exceptions.JSONDecodeError as e:
            self.chat_history.pop()
            logger.error(f"[OllamaGenerator] JSON decode error: {e}")
            # noinspection PyUnboundLocalVariable
            logger.debug(f"[OllamaGenerator] Raw response:\n{response.text}")
            raise RuntimeError(f"OllamaGenerator encountered invalid JSON: {e}")
        except Exception as e:
            self.chat_history.pop()
            logger.error(f"[OllamaGenerator] Failed to generate response: {e}", exc_info=True)
            raise RuntimeError(f"OllamaGenerator encountered an issue: {e}.")
        
        self.chat_history.append({"role": "assistant", "content": response_text})
        logger.debug(f"[OllamaGenerator] Response:\n{response_text}")
        return response_text
    
    @staticmethod
    def format_input(response: str, retrievals: List[str]) -> str:
        return (
            "Response:\n"
            "<<<\n"
            f"{response.strip()}\n"
            ">>>\n\n"
            "Retrievals:\n"
            "<<<\n"
            f"{json.dumps(retrievals, ensure_ascii=False, indent=2)}\n"
            ">>>"
        )
    
    @staticmethod
    def format_output(output: str) -> List[Tuple[bool, str]]:
        output = output.strip()
        fence_match = re.search(r"```(?:json)?\s*(\[\s*[\s\S]*?\s*\])\s*```", output, flags=re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1)
        
        # If still not pure JSON, try to slice the first top-level JSON array
        if not output.lstrip().startswith("["):
            # Find the first '[' and last ']' to capture an array
            start = output.find("[")
            end = output.rfind("]")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("Could not locate a JSON array in model output.")
            output = output[start:end + 1]
        
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse model JSON output: {e}") from e
        
        if not isinstance(data, list):
            raise ValueError("Parsed JSON is not a list (expected an array of objects).")
        
        def to_bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.strip().lower() in {"true", "1", "yes", "y"}
            return bool(v)
        
        # Sort by index and extract (used, reason)
        items = []
        for item in data:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            used = to_bool(item.get("used", False))
            reason = (item.get("reason") or "").strip()
            items.append((idx, used, reason))
        
        # Ensure ordering by index and return only (used, reason)
        items.sort(key=lambda x: (float("inf") if x[0] is None else x[0]))
        return [(used, reason) for _, used, reason in items]
    
    def filter_retrievals(
            self, response: str, retrievals: List[WeaviateSearchChunkResult], compared_property: str,
    ) -> Tuple[List[WeaviateSearchChunkResult], str]:
        formatted_input = self.format_input(response, [r.retrieved_chunk[compared_property] for r in retrievals])
        generated_response = self.generate_response(formatted_input)
        formatted_output = self.format_output(generated_response)
        
        reason = []
        final_retrievals = []
        
        for i, (used, reason_i) in enumerate(formatted_output):
            if used:
                final_retrievals.append(retrievals[i])
            reason.append(f"({i + 1}) [{'used' if used else 'not used'}] {reason_i}\n")
        
        return final_retrievals, "; ".join(reason)


class UsedInAnswerChunkFilter(ChunkFilterProcessor, variant_name="used_in_answer"):
    default_parameters: Dict[str, Any] = {
        **ChunkFilterProcessor.default_parameters,
        "compare_method": "llm",
        "compared_property": "text",
        # cross-encoder method
        "cross_encoder_option_model": "BAAI/bge-reranker-v2-gemma",
        "cross_encoder_option_threshold": 0.6,
        # llm method
        "llm_option_model": "gpt-4.1",
        # embedder method
        "embedding_option_model": "text-embedding-3-large",
        "embedding_option_threshold": 0.6,
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.top_n_template = self.parameters.get("top_n", None)
        self.threshold_template = self.parameters.get("threshold", None)
        self.current_response = self.parameters.get("current_response", "")
        
        self.compare_method = self.parameters.get("compare_method", self.default_parameters["compare_method"]).strip()
        self.compared_property = self.parameters.get("compared_property", self.default_parameters["compared_property"]).strip()
        
        self.llm_option_model = self.parameters.get("llm_option_model", self.default_parameters["llm_option_model"]).strip()
        self.llm_option_api_key = self.parameters.get("llm_option_api_key", None)
        self.llm_option_api_base = self.parameters.get("llm_option_api_base", None)
        self.llm_filter = LLMRelevanceFilter(self.llm_option_model, self.llm_option_api_key, self.llm_option_api_base)
        
        self.cross_encoder_option_model = self.parameters.get(
            "cross_encoder_option_model", self.default_parameters["cross_encoder_option_model"],
        ).strip()
        self.cross_encoder_option_threshold = float(
            self.parameters.get("cross_encoder_option_threshold", self.default_parameters["cross_encoder_option_threshold"]),
        )
        
        self.embedding_option_model = self.parameters.get(
            "embedding_option_model", self.default_parameters["embedding_option_model"],
        ).strip()
        self.embedding_option_threshold = float(
            self.parameters.get("embedding_option_threshold", self.default_parameters["embedding_option_threshold"]),
        )
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "current_response": {
                    "type": "string",
                    "description": "Current response (by generator / system)",
                },
                "compare_method": {
                    "type": "string",
                    "description": "Options: llm (similarity), cross_encoding (with threshold), embedding (with threshold)",
                    "default": "llm",
                },
                "compare_property": {
                    "type": "string",
                    "description": "What to compare",
                    "default": "text",
                },
                # LLM specific
                "llm_option_model": {
                    "type": "string",
                    "description": "Model used to compare answers (only relevant for LLM); Options: [gpt-4.1, gpt-3.5, llama3_3-70b]",
                    "default": "gpt-4.1",
                },
                "llm_option_api_key": {
                    "type": "string",
                    "description": "API key for the chosen LLM (Azure OpenAI for GPT variants).",
                    "default": "",
                },
                "llm_option_api_base": {
                    "type": "string",
                    "description": "API base URL for the chosen LLM (Azure endpoint for GPT variants).",
                    "default": "",
                },
                # Cross encoder specific
                "cross_encoder_option_model": {
                    "type": "string",
                    "description": "Cross-encoder model when rank_method=cross_encoding. "
                                   "Options e.g.: [cross-encoder/ms-marco-MiniLM-L-6-v2, cross-encoder/ms-marco-MiniLM-L-12-v2, "
                                   "BAAI/bge-reranker-base, BAAI/bge-reranker-large, BAAI/bge-reranker-v2-m3, BAAI/bge-reranker-v2-gemma, "
                                   "cross-encoder/stsb-roberta-base]",
                    "default": "BAAI/bge-reranker-v2-gemma",
                },
                "cross_encoder_option_threshold": {
                    "type": "float",
                    "description": "Cutoff in [0,1]. If similarity >= threshold, Chunk is considered as utilized.",
                    "default": 0.6,
                },
                # Embedding specific
                "embedding_option_model": {
                    "type": "string",
                    "description": "Embedding model when rank_method=embedding. "
                                   "Options e.g.: [text-embedding-3-large, baai-llm-embedder, baai-bge-m3, baai-bge-reranker-large]",
                    "default": "text-embedding-3-large",
                },
                "embedding_option_threshold": {
                    "type": "float",
                    "description": "Cutoff in [0,1]. If similarity >= threshold, Chunk is considered as utilized.",
                    "default": 0.6,
                },
            },
        )
        return base_params
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_output_spec()
        base_params.update(
            {
                "used_in_answer.current_response": {
                    "type": "string", "description": "The rendered current response",
                },
                "used_in_answer.llm_reason": {
                    "type": "string", "description": "Reason for filter",
                },
            },
        )
        return base_params
    
    def process(self, _, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        current_response = render_template(self.current_response, data)
        if current_response is None:
            raise ValueError("UsedInAnswerChunkFilter: current_response must be a string to compare answers to.")
        
        if self.compare_method == "cross_encoding":
            ranked = self.advanced_vector_service.rerank(
                reranking_option="cross_encoding",
                query=current_response,
                retrieved_chunks=retrievals,
                cross_encoder=self.cross_encoder_option_model,
                compared_property=self.compared_property,
            )
            return [
                c for c in ranked if c.rerank_score >= self.cross_encoder_option_threshold
            ]
        elif self.compare_method == "embedding":
            ranked = self.advanced_vector_service.rerank(
                reranking_option="embedding",
                query=current_response,
                retrieved_chunks=retrievals,
                embedder=self.embedding_option_model,
                compared_property=self.compared_property,
            )
            return [
                c for c in ranked if c.rerank_score >= self.embedding_option_threshold
            ]
        elif self.compare_method == "llm":
            ranked, reason = self.llm_filter.filter_retrievals(current_response, retrievals, self.compared_property)
            return ranked
        else:
            raise ValueError(f"Unknown compare method: {self.compare_method}")
