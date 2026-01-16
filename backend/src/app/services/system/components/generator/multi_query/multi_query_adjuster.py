import json
import os
import re
from typing import Dict, Any, Tuple, List

from app.models.chat.chat import WorkflowComponentExecutionResult
from app.services.system.components import AbstractComponent, render_template
from app.utils.llama_index.llm_interaction import AzureOpenAILlamaIndexLLM, OllamaLlamaIndexLLM
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
_ADJUST_QUERY_PROMPT = """You are assisting with: {scope}.
Knowledge source: {knowledge_source_description}.

Goal:
Given the QUESTION, generate AT MAXIMUM {num_results} search queries (questions or hypothetical documents) that maximize recall for retrieval while staying within scope.
If not useful, generate less search queries, and be sure all are different.

{queries_description}

Output format (STRICT):
- Return ONLY a JSON array of strings, e.g. ["query one", "query two", ...]
- Do NOT include any surrounding text, code fences, or explanations.
- Each item MUST contain ≥2 content words (≥3 letters each).
- Do NOT output placeholders like "...", ".", "..", ".//", "N/A", "TBD".
- Avoid duplicates; vary phrasing and include synonyms; keep within scope.

Few-shot guidance (optional):
{few_shot_examples}

QUESTION:
{question}
"""


class MultiQueryAdjuster(AbstractComponent, variant_name="multi_query"):
    default_parameters: Dict[str, Any] = {
        # Primary input (templated from the working memory / data dict)
        "question": "f'{start.current_user_input}'",
        
        # Which backend to use: "azure" | "ollama"
        "generator_backend": "azure",
        
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
        
        # Scope & examples
        "scope": "Question-answering system for expert clinicians on topics of Oral and Maxillofacial Surgery (OMFS/MKG) or similar related topics",
        "knowledge_source_description": "Official AWMF Oral and Maxillofacial Surgery (OMFS/MKG) guidelines",
        
        # What and how many to generate
        "num_results": 5,
        "queries_description": "Produce cleaned up questions, alternative phrasings or subqueries, and HyDE documents (concise hypothetical documents in the style of AWMF guidelines) WHERE applicable.",
        
        # Optional structured few-shot examples:
        # Each item is a dict: {"question": "...", "output": ["...","..."]}  (output entries are subqueries)
        "few_shot_examples": [
            {
                "question": "Welche Symptome können im Zusammenhang mit Weisheitszähnen vorkommen?",
                "output": [
                    "Welche Symptome können im Zusammenhang mit Weisheitszähnen vorkommen?",
                    "Klinische und radiologische Symptome im Zusammenhang mit Weisheitszähnen können typischerweise sein: Perikoronitis (Entzündung des Zahnfleischs um den Weisheitszahn), Schmerzen im Bereich des retinierten oder teilretinierten Zahnes, Schwellung, Trismus (Mundöffnungseinschränkung), Foetor ex ore (Mundgeruch), Abszessbildung, Fieber, regionale Lymphadenopathie, Resorptionen an benachbarten Zahnwurzeln, Distalkaries am Nachbarzahn, und Entwicklung von odontogenen Zysten.",
                ],
            },
            {
                "question": "Was ist bei Patienten mitBestrahlungstherapie bei ner Weisheitszahnentfenrung zu tun?",
                "output": [
                    "Was ist bei Patienten mit Bestrahlungstherapie bei einer Weisheitszahnentfernung zu tun?",
                    "Welche besonderen Maßnahmen sind bei der Entfernung von Weisheitszähnen bei Patienten mit vorangegangener Bestrahlungstherapie zu beachten und welche Empfehlungen geben die AWMF-Leitlinien bezüglich Indikationen und Kontraindikationen für eine Weisheitszahnentfernung nach Bestrahlungstherapie?"
                    "Bei Patienten mit vorangegangener Bestrahlungstherapie im Kopf-Hals-Bereich ist vor der Entfernung von Weisheitszähnen eine strenge Indikationsstellung erforderlich. Die Planung sollte interdisziplinär erfolgen. Grundsätzlich sind atraumatische Operationsmethoden mit minimaler Knochenresektion anzustreben. Eine prä- und postoperative antibiotische Abschirmung wird empfohlen. Zur Prophylaxe einer Osteoradionekrose ist ggf. eine adjuvante hyperbare Sauerstofftherapie zu erwägen. Postoperativ ist auf eine engmaschige Nachsorge und Wundkontrolle zu achten. Indikationen zur Weisheitszahnentfernung nach Bestrahlungstherapie bestehen nur bei zwingender Notwendigkeit (z.B. manifester Infektion, nicht beherrschbaren Schmerzen, ausgedehnten Destruktionen). Eine elektive Entfernung sollte vermieden werden, da das Risiko für eine Osteoradionekrose erhöht ist. Kontraindikation besteht bei fehlender dringlicher Indikation, insbesondere im bestrahlten Kieferbereich; in diesen Fällen sollte eine engmaschige Überwachung und konservative Therapie bevorzugt werden. "
                    "Welche präventiven und therapeutischen Strategien werden zur Vermeidung von Komplikationen wie Osteoradionekrose bei Weisheitszahnentfernung nach Bestrahlungstherapie empfohlen?",
                    "Zur Vermeidung einer Osteoradionekrose nach Bestrahlungstherapie sind folgende präventive und therapeutische Strategien empfohlen: Eine gründliche zahnärztliche Sanierung sollte möglichst vor Beginn der Strahlentherapie erfolgen. Nach Bestrahlung sind Extraktionen, insbesondere von Weisheitszähnen, streng zu indizieren und – wenn unvermeidbar – unter antibiotischer Abschirmung und atraumatischer Technik durchzuführen. Die Indikation zur Entfernung sollte kritisch gestellt und, wenn möglich, auf einen Zeitraum vor Strahlenbeginn gelegt werden. Nach der Extraktion ist eine primäre Weichgewebsdeckung anzustreben. Eine hyperbare Sauerstofftherapie kann im Einzelfall erwogen werden. Regelmäßige Nachsorge und frühzeitige Intervention bei Wundheilungsstörungen sind essenziell.",
                ],
            },
        ],
    }
    
    def __init__(self, component_id, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.next_component_id = None
        self.llm = None
        
        p: Dict[str, Any] = {**self.default_parameters, **(parameters or {})}
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
        
        # Persist effective config for later inspection/debugging
        self.config = {
            "generator_backend": backend,
            "num_results": int(p.get("num_results", 5)),
            "scope": p.get("scope"),
            "knowledge_source_description": p.get("knowledge_source_description"),
        }
    
    def set_next_component(self, next_component_id: str):
        self.next_component_id = next_component_id
    
    def load_execution_result(self, result: WorkflowComponentExecutionResult):
        """Hook for restoring from a stored result (optional in this component)."""
        pass
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        
        multi_query_params = {
            "question": {
                "type": "string",
                "description": "Template for the user question (Jinja/py f-string via render_template).",
                "default": "f'{start.current_user_input}'",
            },
            "num_results": {
                "type": "integer",
                "description": "Maximum number of items to generate.",
                "default": 5,
            },
            "scope": {
                "type": "string",
                "description": "High-level scope/purpose of the system.",
            },
            "knowledge_source_description": {
                "type": "string",
                "description": "Brief description of the underlying knowledge source.",
            },
            "queries_description": {
                "type": "string",
                "description": "Instruction text describing the desired search strings. Output must remain a JSON array of strings.",
            },
            "few_shot_examples": {
                "type": "array",
                "description": "Optional list of few-shot examples. Each item: {'question': str, 'output': List[str]}",
            },
            "generator_backend": {
                "type": "string",
                "description": "LLM backend to use.",
                "enum": ["azure", "ollama"],
                "default": "azure",
            },
        }
        
        # Azure settings
        gen_azure_params = {
            "azure_api_key": {"type": "string", "description": "Azure OpenAI API key."},
            "azure_api_base": {"type": "string", "description": "Azure OpenAI endpoint, e.g., https://<resource>.openai.azure.com"},
            "azure_api_version": {"type": "string", "description": "Azure OpenAI API version.", "default": "2024-08-01-preview"},
            "azure_chat_deployment": {"type": "string", "description": "Azure chat deployment name (e.g., 'gpt-4.1' or 'gpt-4o')."},
            "azure_temperature": {"type": "number", "description": "Sampling temperature.", "default": 0.7},
            "azure_max_tokens": {"type": "integer", "description": "Max tokens (completion).", "default": 512},
        }
        
        # Ollama settings
        gen_ollama_params = {
            "ollama_api_base": {"type": "string", "description": "Ollama base URL.", "default": "http://localhost:11434"},
            "ollama_model": {"type": "string", "description": "Ollama model name.", "default": "llama3.3:70b"},
            "ollama_temperature": {"type": "number", "description": "Sampling temperature.", "default": 0.7},
            "ollama_max_tokens": {"type": "integer", "description": "Num tokens to predict.", "default": 512},
        }
        
        return {**base_params, **multi_query_params, **gen_azure_params, **gen_ollama_params}
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_output_spec()
        base.update(
            {
                "multi_query.search_queries": {
                    "type": "list",
                    "description": "List of generated queries (strings).",
                },
                "multi_query.raw_response": {
                    "type": "string",
                    "description": "Raw LLM response for debugging/traceability.",
                },
            },
        )
        return base
    
    def _llm_complete(self, prompt: str) -> str:
        """Robust completion wrapper handling different LLM wrapper interfaces."""
        if hasattr(self.llm, "complete"):
            resp = self.llm.complete(prompt)
        elif hasattr(self.llm, "predict"):
            resp = self.llm.predict(prompt)
        elif hasattr(self.llm, "__call__"):
            resp = self.llm(prompt)
        else:
            raise RuntimeError("LLM wrapper does not expose a callable completion method.")
        
        # Normalize response to text
        if isinstance(resp, str):
            return resp
        if hasattr(resp, "text"):
            return resp.text
        if hasattr(resp, "message"):
            return getattr(resp, "message") or ""
        if isinstance(resp, dict):
            return resp.get("text") or resp.get("message") or json.dumps(resp)
        return str(resp)
    
    @staticmethod
    def _render_prompt(
            question: str,
            num_results: int,
            scope: str,
            knowledge_source_description: str,
            examples: List[Dict[str, Any]],
            queries_description: str,
    ) -> str:
        # Render few-shot section (plain text guidance)
        rendered_examples: List[str] = []
        for i, ex in enumerate(examples or []):
            q = (ex.get("question") or "").strip()
            outputs = ex.get("output") or []
            out_lines = "\n  - " + "\n  - ".join([str(o).strip() for o in outputs if str(o).strip()])
            rendered_examples.append(f"Example {i + 1}:\nQuestion: {q}\nOutput:{out_lines}")
        few_shot_examples = "\n\n".join(rendered_examples) if rendered_examples else "(none)"
        
        return _ADJUST_QUERY_PROMPT.format(
            scope=scope,
            knowledge_source_description=knowledge_source_description,
            num_results=num_results,
            queries_description=queries_description,
            few_shot_examples=few_shot_examples,
            question=question.strip(),
        )
    
    # --- Sanitizers ---
    
    @staticmethod
    def _normalize(s: str) -> str:
        s = re.sub(r"\s+", " ", s)
        s = s.strip(" \t\r\n'\"`*·•-–—.,;:()[]{}")
        return s.strip()
    
    @staticmethod
    def _is_degenerate(s: str) -> bool:
        if not s:
            return True
        if s in {".", "..", "...", "./", ".//", "/", "\\", "''", '""', "`", "—", "-", "N/A", "TBD"}:
            return True
        if len(s) < 5:
            return True
        if not re.search(r"[A-Za-zÄÖÜäöüß]", s):
            return True
        # require at least 2 content words (>=3 letters)
        words = re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", s)
        if len(words) < 2:
            return True
        punct = len(re.findall(r"[^\w\sÄÖÜäöüß]", s))
        if punct / max(len(s), 1) > 0.5:
            return True
        return False
    
    @staticmethod
    def _extract_items(raw_text: str) -> List[str]:
        """
        Extract a list of strings from LLM output.
        Primary: JSON array of strings.
        Fallbacks:
            - Comma-separated list
            - Bulleted/numbered lines
            - Non-empty lines (last resort)
        """
        if not raw_text:
            return []
        
        text = raw_text.strip()
        
        def sanitize_and_dedupe(items: List[str]) -> List[str]:
            out, seen = [], set()
            for it in items:
                itn = MultiQueryAdjuster._normalize(str(it))
                if MultiQueryAdjuster._is_degenerate(itn):
                    continue
                key = itn.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(itn)
            return out
        
        # 1) JSON array (strict contract)
        try:
            arr_match = re.search(r"\[[\s\S]*\]", text)
            if arr_match:
                arr = json.loads(arr_match.group(0))
                if isinstance(arr, list):
                    qs = [x for x in arr if isinstance(x, (str, int, float))]
                    qs = [str(x) for x in qs]
                    cleaned = sanitize_and_dedupe(qs)
                    if cleaned:
                        return cleaned
        except Exception:
            pass
        
        # 2) Comma-separated list on a single line
        if "," in text and "[" not in text and "<" not in text:
            parts = [p.strip() for p in text.split(",")]
            cleaned = sanitize_and_dedupe(parts)
            if cleaned:
                return cleaned
        
        # 3) Bulleted/numbered lines
        lines = [ln.strip() for ln in text.splitlines()]
        candidates = []
        for ln in lines:
            m = re.match(r"^(\-|\*|\d+[\.\)])\s+(.*)$", ln)
            if m:
                candidates.append(m.group(2).strip())
        if not candidates:
            # 4) As a last resort, take all non-empty lines
            candidates = [ln for ln in lines if ln]
        
        return sanitize_and_dedupe(candidates)
    
    def execute(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        p = {**self.default_parameters, **(self.parameters or {})}
        
        question_template = p.get("question") or self.default_parameters.get("question")
        num_results = p["num_results"]
        scope = p.get("scope") or self.default_parameters["scope"]
        knowledge_source_description = p["knowledge_source_description"]
        few_shot_examples = p.get("few_shot_examples") or []
        queries_description = p["queries_description"]
        
        try:
            question = render_template(question_template, data)
        except Exception:
            logger.exception("Failed to render question template.")
            raise
        
        prompt = self._render_prompt(
            question=question,
            num_results=num_results,
            scope=scope,
            knowledge_source_description=knowledge_source_description,
            examples=few_shot_examples,
            queries_description=queries_description,
        )
        
        try:
            full_response = self._llm_complete(prompt)
        except Exception:
            logger.exception("LLM generation failed.")
            raise
        
        # Extract queries
        queries = self._extract_items(full_response)
        
        if not queries:
            logger.warning("No valid queries extracted; falling back to original question.")
            queries = [self._normalize(question)]
        
        if len(queries) > num_results:
            queries = queries[:num_results]
        
        data[f"{self.id}.raw_response"] = full_response
        data[f"{self.id}.search_queries"] = queries
        
        return data, self.next_component_id
