from typing import Any, Dict, List, Optional

from app.models.tools.llm_interaction import LLMSettings
from app.models.tools.snomed_interaction import SnomedSettings
from app.services.service_registry import get_keyword_service, get_snomed_service
from app.services.system.components.query_transformer.abstract_query_transformer import AbstractQueryTransformer
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template

logger = setup_logger(__name__)


class KeywordQueryTransformer(AbstractQueryTransformer, variant_name="keyword_extractor"):
    default_parameters: Dict[str, Any] = {
        **AbstractQueryTransformer.default_parameters,
        "extraction_method": "yake",
        "expand_with_synonyms": False,
        "include_original_keyword": True,
        "allow_english_fallback": True,
        "min_keywords": 3,
        "max_keywords": 10,
        "language": "de",
        "max_n_gram_size": 3,
        "deduplication_threshold": 0.9,
        "ignore_terms": ["Tabelle", "Abbildung", "Leitlinie"],
        "suppress_subphrases": True,
        "headroom": 5,
        "scope_description": "German guidelines for Oral and Maxillofacial surgery from the AWMF.",
        "guidance_additions": [
            "Prefer multi-word medical terms, diagnoses, procedures, imaging, therapies, risk factors, patient groups, and staging systems.",
        ],
        "important_terms": [
            "indiziert",
            "Indikation",
            "nicht",
            "soll",
            "sollte",
            "empfehlenswert",
        ],
        "examples": [],
        "llm_settings": None,
        "snomed_settings": {},
    }
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "extraction_method": {
                    "type": "string",
                    "description": "Keyword extraction method: 'yake' or 'llm'.",
                    "default": "yake",
                },
                "expand_with_synonyms": {
                    "type": "bool",
                    "description": "If true, expand extracted keywords through SNOMED synonyms.",
                    "default": False,
                },
                "include_original_keyword": {
                    "type": "bool",
                    "description": "If synonym expansion is enabled, keep each original keyword in the expanded output.",
                    "default": True,
                },
                "allow_english_fallback": {
                    "type": "bool",
                    "description": "Allow English translation fallback during SNOMED synonym expansion.",
                    "default": True,
                },
                "min_keywords": {
                    "type": "int",
                    "description": "Requested minimum number of extracted keywords.",
                    "default": 3,
                },
                "max_keywords": {
                    "type": "int",
                    "description": "Maximum number of extracted keywords.",
                    "default": 10,
                },
                "language": {
                    "type": "string",
                    "description": "Language used by YAKE.",
                    "default": "de",
                },
                "max_n_gram_size": {
                    "type": "int",
                    "description": "Maximum n-gram size for YAKE extraction.",
                    "default": 3,
                },
                "deduplication_threshold": {
                    "type": "float",
                    "description": "YAKE deduplication threshold.",
                    "default": 0.9,
                },
                "ignore_terms": {
                    "type": "list",
                    "description": "Terms that should be ignored after normalization.",
                },
                "suppress_subphrases": {
                    "type": "bool",
                    "description": "If true, drop keywords that are complete subphrases of longer kept phrases.",
                    "default": True,
                },
                "headroom": {
                    "type": "int",
                    "description": "Extra YAKE candidates requested before post-filtering.",
                    "default": 5,
                },
                "scope_description": {
                    "type": "string",
                    "description": "Domain hint used by the LLM extraction method.",
                },
                "guidance_additions": {
                    "type": "list",
                    "description": "Additional guidance bullets for LLM-based keyword extraction.",
                },
                "important_terms": {
                    "type": "list",
                    "description": "Terms to emphasize in LLM-based keyword extraction.",
                },
                "examples": {
                    "type": "list",
                    "description": "Few-shot examples for LLM-based keyword extraction.",
                },
                "llm_settings": {
                    "type": "object",
                    "description": "Required for LLM extraction and synonym expansion.",
                },
                "snomed_settings": {
                    "type": "object",
                    "description": "Optional SNOMED CT settings used for synonym expansion.",
                    "default": {},
                },
            },
        )
        return base
    
    @classmethod
    def get_output_spec(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_output_spec()
        base.update(
            {
                "query_transformer.keywords": {
                    "type": "list",
                    "description": "Extracted keywords before optional synonym expansion.",
                },
                "query_transformer.expanded_keywords": {
                    "type": "list",
                    "description": "Flattened keyword list after optional synonym expansion.",
                },
                "query_transformer.keyword_expansions": {
                    "type": "list",
                    "description": "Detailed SNOMED expansion metadata per keyword.",
                },
            },
        )
        return base
    
    def _resolve_llm_settings(self) -> Optional[LLMSettings]:
        raw = self.parameters.get("llm_settings")
        if raw is None:
            return None
        return LLMSettings.model_validate(raw)
    
    def _extract_keywords(self, query: str) -> List[str]:
        method = str(self.parameters.get("extraction_method", self.default_parameters["extraction_method"])).strip().lower()
        keyword_service = get_keyword_service()
        
        if method == "yake":
            return keyword_service.extract_yake(
                text=query,
                language=self.parameters.get("language", self.default_parameters["language"]),
                min_keywords=self.parameters.get("min_keywords", self.default_parameters["min_keywords"]),
                max_keywords=self.parameters.get("max_keywords", self.default_parameters["max_keywords"]),
                max_n_gram_size=self.parameters.get("max_n_gram_size", self.default_parameters["max_n_gram_size"]),
                deduplication_threshold=self.parameters.get(
                    "deduplication_threshold",
                    self.default_parameters["deduplication_threshold"],
                ),
                ignore_terms=self.parameters.get("ignore_terms", self.default_parameters["ignore_terms"]),
                suppress_subphrases=self.parameters.get(
                    "suppress_subphrases",
                    self.default_parameters["suppress_subphrases"],
                ),
                headroom=self.parameters.get("headroom", self.default_parameters["headroom"]),
            )
        
        if method == "llm":
            llm_settings = self._resolve_llm_settings()
            if llm_settings is None:
                raise ValueError("Keyword extraction method 'llm' requires parameters.llm_settings.")
            
            return keyword_service.extract_llm(
                text=query,
                llm_settings=llm_settings,
                scope_description=self.parameters.get("scope_description", self.default_parameters["scope_description"]),
                guidance_additions=self.parameters.get("guidance_additions", self.default_parameters["guidance_additions"]),
                ignore_terms=self.parameters.get("ignore_terms", self.default_parameters["ignore_terms"]),
                important_terms=self.parameters.get("important_terms", self.default_parameters["important_terms"]),
                examples=self.parameters.get("examples", self.default_parameters["examples"]),
                min_keywords=self.parameters.get("min_keywords", self.default_parameters["min_keywords"]),
                max_keywords=self.parameters.get("max_keywords", self.default_parameters["max_keywords"]),
            )
        
        raise ValueError("Unsupported extraction_method. Available: ['yake', 'llm']")
    
    def _expand_keywords(self, keywords: List[str]) -> Dict[str, Any]:
        if not self.parameters.get("expand_with_synonyms", self.default_parameters["expand_with_synonyms"]):
            return {
                "expanded_keywords": list(keywords),
                "keyword_expansions": [],
            }
        
        llm_settings = self._resolve_llm_settings()
        if llm_settings is None:
            raise ValueError("Keyword synonym expansion requires parameters.llm_settings.")
        
        snomed_settings = SnomedSettings.model_validate(
            self.parameters.get("snomed_settings", self.default_parameters["snomed_settings"]),
        )
        include_original = self.parameters.get(
            "include_original_keyword",
            self.default_parameters["include_original_keyword"],
        )
        allow_english_fallback = self.parameters.get(
            "allow_english_fallback",
            self.default_parameters["allow_english_fallback"],
        )
        
        items = get_snomed_service().expand_keywords(
            keywords,
            llm_settings=llm_settings,
            snomed_settings=snomed_settings,
            allow_english_fallback=allow_english_fallback,
            include_original=include_original,
        )
        
        expanded_keywords: List[str] = []
        seen = set()
        for item in items:
            for term in item.expanded_terms:
                normalized = " ".join(term.lower().split())
                if normalized in seen:
                    continue
                seen.add(normalized)
                expanded_keywords.append(term)
        
        return {
            "expanded_keywords": expanded_keywords,
            "keyword_expansions": [item.model_dump() for item in items],
        }
    
    def execute(self, data: Dict[str, Any]):
        query_template = self.parameters.get("query", self.default_parameters["query"])
        query = render_template(query_template, data)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Resolved query must not be empty")
        method = str(self.parameters.get("extraction_method", self.default_parameters["extraction_method"])).strip().lower()
        expand_with_synonyms = bool(
            self.parameters.get("expand_with_synonyms", self.default_parameters["expand_with_synonyms"]),
        )
        logger.debug(
            "KeywordQueryTransformer.execute: component_id=%s method=%s expand_with_synonyms=%s query_chars=%d",
            self.id,
            method,
            expand_with_synonyms,
            len(query),
        )
        
        keywords = self._extract_keywords(query)
        expansion_outputs = self._expand_keywords(keywords)
        query_outputs = self._build_common_outputs(query, expansion_outputs["expanded_keywords"])
        
        outputs = {
            **query_outputs,
            "keywords": keywords,
            "expanded_keywords": expansion_outputs["expanded_keywords"],
            "keyword_expansions": expansion_outputs["keyword_expansions"],
        }
        
        for key, value in outputs.items():
            data[f"{self.id}.{key}"] = value
        logger.info(
            "KeywordQueryTransformer succeeded: component_id=%s keywords=%d expanded_keywords=%d",
            self.id,
            len(keywords),
            len(expansion_outputs["expanded_keywords"]),
        )
        
        return data, self.next_component_id
