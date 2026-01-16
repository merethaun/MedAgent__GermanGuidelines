from typing import Optional, List, Dict, Literal

from pydantic import Field, BaseModel


class LLMSettings(BaseModel):
    model: Literal["gpt-5", "gpt-4.1", "o3", "llama3_3-70b"] = Field(
        default="gpt-4.1", description="LLM backend to use.",
    )
    api_key: Optional[str] = Field(default=None, description="Overrides env; optional.")
    api_base: Optional[str] = Field(default=None, description="API base URL; optional.")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)


class KeywordLLMSettings(LLMSettings):
    # Preferred phrase-length hints and hard cap
    min_keywords: Optional[int] = Field(default=None, ge=1)
    max_keywords: Optional[int] = Field(default=None, ge=1)
    
    # settings for search
    ignore_terms: Optional[List[str]] = None
    important_terms: Optional[List[str]] = None
    
    # Prompt settings (map to your extract_llm signature)
    scope_description: Optional[str] = None
    guidance_additions: Optional[List[str]] = None
    examples: Optional[List[Dict]] = None


class YAKESettings(BaseModel):
    language: str = Field(
        default="de", description="Language of the text to extract keywords from.",
    )
    # Preferred phrase-length hints and hard cap
    min_keywords: Optional[int] = Field(default=None, ge=1)
    max_keywords: Optional[int] = Field(default=None, ge=1)
    ignore_terms: Optional[List[str]] = Field(
        default=None, description="List of terms to ignore when extracting keywords.",
    )
    max_n_gram_size: Optional[int] = Field(
        default=3, description="Maximum n-gram size to consider.",
    )
    deduplication_threshold: Optional[float] = Field(
        default=0.9, description="Threshold for deduplication of keywords.",
    )


class ExtractKeywordsRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw text to extract keywords from.")
    method: Literal["yake", "llm"] = Field(default="yake")
    
    yake: Optional[YAKESettings] = Field(
        default=None,
        description="Required when method='yake'. Contains model + prompt settings.",
    )
    
    llm: Optional[KeywordLLMSettings] = Field(
        default=None,
        description="Required when method='llm'. Contains model + prompt settings.",
    )


class KeywordsForReferenceRequest(BaseModel):
    keyword_method: Literal["yake", "llm"] = Field(default="yake")
    yake: Optional[YAKESettings] = Field(
        default=None,
        description="Required when method='yake'. Contains model + prompt settings.",
    )
    llm_keywords: Optional[KeywordLLMSettings] = Field(
        default=None,
        description="Required when method='llm'. Contains model + prompt settings.",
    )
    apply_synonym_expansion: bool = False
    synonym_expansion_llm: Optional[LLMSettings] = None
    allow_english_search: bool = False
    min_synonym_llm_confidence: float = 0.0
