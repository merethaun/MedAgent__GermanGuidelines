from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.constants.snomed_config import (
    SNOMED_BASE_URL,
    SNOMED_DISPLAY_LANGUAGE_DE,
    SNOMED_DISPLAY_LANGUAGE_EN,
    SNOMED_MAX_RESULTS,
    SNOMED_TIMEOUT_S,
    SNOMED_VALUE_SET_URL,
    SNOMED_VERSION,
)
from app.models.tools.llm_interaction import LLMSettings


class SnomedSettings(BaseModel):
    base_url: str = Field(
        default=SNOMED_BASE_URL,
        description="Base URL of the SNOMED CT FHIR endpoint, for example http://localhost:8080/fhir.",
    )
    value_set_url: str = Field(
        default=SNOMED_VALUE_SET_URL,
        description="FHIR ValueSet URL used for lookup via ValueSet/$expand.",
    )
    version: Optional[str] = Field(
        default=SNOMED_VERSION,
        description="SNOMED CT system-version URI used for lookup. Defaults to the German edition loaded in Docker.",
    )
    display_language_de: str = Field(SNOMED_DISPLAY_LANGUAGE_DE, description="Preferred language tag for German lookup.")
    display_language_en: str = Field(SNOMED_DISPLAY_LANGUAGE_EN, description="Preferred language tag for English fallback lookup.")
    max_results: int = Field(SNOMED_MAX_RESULTS, ge=1, le=100, description="Maximum number of SNOMED matches returned by the FHIR server.")
    timeout_s: int = Field(SNOMED_TIMEOUT_S, ge=1, le=120, description="Request timeout for SNOMED CT lookups.")
    headers: Dict[str, str] = Field(default_factory=dict, description="Optional extra headers for the SNOMED server.")


class SnomedSynonym(BaseModel):
    synonym: str
    preference: float = Field(1.0, ge=0.0, le=1.0)


class SnomedCanonicalTerm(BaseModel):
    queried_term: str
    matched_term: Optional[str] = None
    canonical_form: Optional[str] = None
    concept_id: Optional[str] = None
    translated_via_llm: bool = False


class SnomedTermRequest(BaseModel):
    term: str = Field(..., description="Medical term to resolve.")
    llm_settings: LLMSettings = Field(..., description="LLM settings used for translation fallback.")
    snomed_settings: SnomedSettings = Field(
        default_factory=SnomedSettings,
        description="SNOMED CT instance settings for this request. Defaults to the local snomed-lite setup.",
    )
    allow_english_fallback: bool = Field(
        True,
        description="If true, translate the term to English and retry when German lookup returns no result.",
    )


class SnomedSynonymsResponse(BaseModel):
    queried_term: str
    matched_term: Optional[str] = None
    canonical_form: Optional[str] = None
    concept_id: Optional[str] = None
    translated_via_llm: bool = False
    synonyms: List[SnomedSynonym]


class SnomedKeywordExpansionRequest(BaseModel):
    keywords: List[str] = Field(..., min_length=1, description="Keywords that should be expanded with SNOMED synonyms.")
    llm_settings: LLMSettings = Field(..., description="LLM settings used for translation fallback.")
    snomed_settings: SnomedSettings = Field(
        default_factory=SnomedSettings,
        description="SNOMED CT instance settings for this request. Defaults to the local snomed-lite setup.",
    )
    allow_english_fallback: bool = Field(True, description="Use English translation fallback if German lookup misses.")
    include_original: bool = Field(True, description="Keep the original keywords in the final expanded list.")


class SnomedKeywordExpansionItem(BaseModel):
    keyword: str
    concept_id: Optional[str] = None
    canonical_form: Optional[str] = None
    expanded_terms: List[str]
    translated_via_llm: bool = False


class SnomedKeywordExpansionResponse(BaseModel):
    expanded_keywords: List[str]
    items: List[SnomedKeywordExpansionItem]


class SnomedMedicalKeywordRequest(BaseModel):
    text: str = Field(..., description="Clinical input text.")
    llm_settings: LLMSettings = Field(..., description="LLM settings used for extraction and translation fallback.")
    snomed_settings: Optional[SnomedSettings] = Field(
        default_factory=SnomedSettings,
        description="SNOMED CT settings for canonical enrichment. Defaults to the local snomed-lite setup.",
    )
    max_keywords: int = Field(20, ge=1, le=100, description="Maximum number of extracted medical keywords.")
    resolve_canonical: bool = Field(
        True,
        description="If true and SNOMED settings are provided, extracted keywords are enriched with canonical forms.",
    )
    allow_english_fallback: bool = Field(True, description="Use English translation fallback during canonical enrichment.")


class SnomedMedicalKeywordItem(BaseModel):
    keyword: str
    canonical_form: Optional[str] = None
    concept_id: Optional[str] = None
    translated_via_llm: bool = False


class SnomedMedicalKeywordResponse(BaseModel):
    keywords: List[SnomedMedicalKeywordItem]


class SnomedVersionsRequest(BaseModel):
    snomed_settings: SnomedSettings = Field(
        default_factory=SnomedSettings,
        description="SNOMED CT instance settings for version discovery. Defaults to the local snomed-lite setup.",
    )


class SnomedVersionInfo(BaseModel):
    version: str
    title: Optional[str] = None
    url: Optional[str] = None


class SnomedVersionsResponse(BaseModel):
    versions: List[SnomedVersionInfo]
    source: str = Field(..., description="FHIR endpoint used to derive the version list, e.g. CodeSystem or metadata.")
