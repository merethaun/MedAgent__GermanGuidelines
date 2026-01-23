from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.tools.llm_interaction import LLMSettings


class KeywordYakeRequest(BaseModel):
    text: str = Field(..., description="Input text passage (German guideline excerpt).")
    language: str = Field("de", description="YAKE language code (e.g., 'de').")
    
    min_keywords: Optional[int] = Field(None, ge=1, description="Desired minimum number of keywords.")
    max_keywords: Optional[int] = Field(None, ge=1, description="Hard cap on number of keywords.")
    
    max_n_gram_size: int = Field(3, ge=1, le=6, description="Max n-gram length for YAKE.")
    deduplication_threshold: float = Field(0.9, ge=0.0, le=1.0, description="YAKE deduplication threshold.")
    ignore_terms: Optional[List[str]] = Field(None, description="Additional noise terms to ignore.")
    suppress_subphrases: bool = Field(True, description="Drop single terms if they appear inside longer phrases.")
    headroom: int = Field(5, ge=0, le=50, description="Extra candidates to request to offset filtering.")


class KeywordLLMRequest(BaseModel):
    text: str = Field(..., description="Input text passage (German guideline excerpt).")
    llm_settings: LLMSettings = Field(..., description="LLM settings used by KeywordService.extract_llm().")
    
    # Optional overrides
    scope_description: Optional[str] = Field(None, description="Scope added into the prompt.")
    guidance_additions: Optional[List[str]] = Field(None, description="Additional prompt guidance bullets.")
    ignore_terms: Optional[List[str]] = Field(None, description="Additional noise terms to ignore.")
    important_terms: Optional[List[str]] = Field(None, description="Terms that indicate important phrasing.")
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="Few-shot examples (same structure as defaults).")
    
    min_keywords: Optional[int] = Field(None, ge=1, description="Minimum desired keywords.")
    max_keywords: Optional[int] = Field(None, ge=1, description="Maximum desired keywords.")


class KeywordExtractionResponse(BaseModel):
    keywords: List[str]


class KeywordBothResponse(BaseModel):
    yake: List[str]
    llm: List[str]
    overlap: List[str]
    union: List[str]
