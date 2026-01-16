from typing import Dict, Any, Optional, List

from app.services.knowledge.guidelines.keywords.keyword_service import KeywordService
from app.services.system.components.generator.keyword import AbstractKeywordExtractor
from app.utils.service_creators import get_keyword_service


class YAKEKeywordExtractor(AbstractKeywordExtractor, variant_name="yake_extractor"):
    """YAKE-based keyword extractor.
    Uses `KeywordService.extract_yake` under the hood.
    """
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: Optional[str] = None):
        super().__init__(component_id, name, parameters, variant)
        
        self.service: KeywordService = get_keyword_service()
        
        # Defaults tuned for German clinical guideline text.
        self.language: str = self.parameters.get("language", "de")
        self.min_keywords: Optional[int] = self.parameters.get("min_keywords", 5)
        self.max_keywords: Optional[int] = self.parameters.get("max_keywords", 20)
        self.max_n_gram_size: int = self.parameters.get("max_n_gram_size", 3)
        self.deduplication_threshold: float = self.parameters.get("deduplication_threshold", 0.9)
        self.ignore_terms: Optional[List[str]] = self.parameters.get("ignore_terms", ["Tabelle", "Abbildung", "Leitlinie"])
        self.suppress_subphrases: bool = self.parameters.get("suppress_subphrases", True)
        self.headroom: int = self.parameters.get("headroom", 5)
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base = super().get_init_parameters()
        base.update(
            {
                "language": {
                    "type": "string",
                    "description": "Language code for YAKE (e.g., 'de', 'en').",
                    "default": "de",
                },
                "min_keywords": {
                    "type": "int",
                    "description": "Best-effort minimum number of keywords to return.",
                    "default": 5,
                },
                "max_keywords": {
                    "type": "int",
                    "description": "Hard cap on number of returned keywords.",
                    "default": 20,
                },
                "max_n_gram_size": {
                    "type": "int",
                    "description": "Maximum n-gram size for YAKE extraction.",
                    "default": 3,
                },
                "deduplication_threshold": {
                    "type": "float",
                    "description": "YAKE deduplication threshold (higher = more deduplication).",
                    "default": 0.9,
                },
                "ignore_terms": {
                    "type": "list",
                    "description": "Case-insensitive terms to drop after normalization.",
                    "default": ["Tabelle", "Abbildung", "Leitlinie"],
                },
                "suppress_subphrases": {
                    "type": "bool",
                    "description": "If true, drop phrases that are whole-word substrings of longer kept phrases.",
                    "default": True,
                },
                "headroom": {
                    "type": "int",
                    "description": "Extra candidates to request from YAKE to offset filtering losses.",
                    "default": 5,
                },
            },
        )
        
        return base
    
    def extract(self, text: str, data: Dict[str, Any]) -> List[str]:
        keywords = self.service.extract_yake(
            text=text, language=self.language, min_keywords=self.min_keywords, max_keywords=self.max_keywords,
            max_n_gram_size=self.max_n_gram_size, deduplication_threshold=self.deduplication_threshold, ignore_terms=self.ignore_terms,
            suppress_subphrases=self.suppress_subphrases, headroom=self.headroom,
        )
        
        return keywords
