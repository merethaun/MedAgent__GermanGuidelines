from typing import List, Optional, Dict, Any, Literal

from app.services.knowledge.guidelines.keywords.keyword_service import KeywordService
from app.services.system.components.generator.keyword import AbstractKeywordExtractor
from app.utils.service_creators import get_keyword_service


class LLMKeywordExtractor(AbstractKeywordExtractor, variant_name="llm_extractor"):
    """LLM-based keyword extractor.
    Uses `KeywordService.extract_llm` with Azure OpenAI or Ollama backends via LlamaIndex wrappers.
    """
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: Optional[str] = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.service: KeywordService = get_keyword_service()
        
        # Reasonable, explicit defaults (aligned with provided KeywordService).
        self.model: Literal["gpt-5", "gpt-4.1", "o3", "llama3_3-70b"] = self.parameters.get("model", "gpt-4.1")
        self.api_key: Optional[str] = self.parameters.get("api_key")
        self.api_base: Optional[str] = self.parameters.get("api_base")
        self.temperature: float = self.parameters.get("temperature", 0.2)
        self.max_tokens: int = self.parameters.get("max_tokens", 512)
        
        self.scope_description: str = self.parameters.get("scope_description", "German guidelines for Oral and Maxillofacial surgery from the AWMF.")
        self.guidance_additions: List[str] = self.parameters.get(
            "guidance_additions",
            [
                "Prefer multi-word medical terms, diagnoses, procedures, imaging, therapies, risk factors, patient groups, and staging systems.",
                "Keep names that are relevant to characterize the text.",
            ],
        )
        self.ignore_terms: List[str] = self.parameters.get("ignore_terms", ["Tabelle", "Abbildung", "Leitlinie"])
        self.important_terms: List[str] = self.parameters.get(
            "important_terms",
            [
                "kann bestehen", "besteht", "indiziert", "Indikation", "kann", "sollte", "keine", "nicht", "soll", "können", "sollten", "notwendig",
                "empfehlenswert", "empfehlen", "sollten",
            ],
        )
        self.examples: List[Dict[str, Any]] = self.parameters.get(
            "examples",
            [
                {
                    "text": "Welche Symptome können im Zusammenhang mit Weisheitszähne vorkommen?",
                    "keywords": ["Symptome", "können", "Weisheitszähne"],
                },
            ],
        )
        self.min_keywords: Optional[int] = self.parameters.get("min_keywords", 5)
        self.max_keywords: Optional[int] = self.parameters.get("max_keywords", 20)
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "model": {
                    "type": "string",
                    "description": "LLM to use: one of {'gpt-5-chat','gpt-4.1','gpt-3.5','llama3_3-70b'}.",
                    "default": "gpt-4.1",
                },
                "api_key": {
                    "type": "string",
                    "description": "API key (optional; falls back to env).",
                    "default": None,
                },
                "api_base": {
                    "type": "string",
                    "description": "API base/endpoint (optional; falls back to env).",
                    "default": None,
                },
                "temperature": {
                    "type": "float",
                    "description": "LLM sampling temperature.",
                    "default": 0.2,
                },
                "max_tokens": {
                    "type": "int",
                    "description": "Max tokens for the completion.",
                    "default": 512,
                },
                "scope_description": {
                    "type": "string",
                    "description": "Domain/scope hint for the prompt.",
                    "default": "German guidelines for Oral and Maxillofacial surgery from the AWMF. ",
                },
                "guidance_additions": {
                    "type": "list",
                    "description": "Bullet guidance items for the prompt.",
                    "default": [
                        "Prefer multi-word medical terms, diagnoses, procedures, imaging, therapies, risk factors, patient groups, "
                        "and staging systems.",
                    ],
                },
                "ignore_terms": {
                    "type": "list",
                    "description": "Terms to ignore after normalization.",
                    "default": ["Tabelle", "Abbildung", "Leitlinie"],
                },
                "important_terms": {
                    "type": "list",
                    "description": "Terms to prioritize if they appear within candidates.",
                    "default": "List read from guidelines",
                },
                "examples": {
                    "type": "list",
                    "description": "Few-shot examples to anchor the output format.",
                    "default": "Some question example",
                },
                "min_keywords": {
                    "type": "int",
                    "description": "Requested minimum keyword count (best-effort).",
                    "default": 5,
                },
                "max_keywords": {
                    "type": "int",
                    "description": "Hard cap on number of returned keywords.",
                    "default": 20,
                },
            },
        )
        return base
    
    def extract(self, text: str, data: Dict[str, Any]) -> List[str]:
        keywords = self.service.extract_llm(
            text=text, model=self.model, api_key=self.api_key, api_base=self.api_base, temperature=self.temperature,
            max_tokens=int(self.max_tokens), scope_description=self.scope_description, guidance_additions=self.guidance_additions,
            ignore_terms=self.ignore_terms, important_terms=self.important_terms, examples=self.examples,
            min_keywords=self.min_keywords, max_keywords=self.max_keywords,
        )
        return keywords
