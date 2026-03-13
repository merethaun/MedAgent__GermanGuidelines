import json
import re
from typing import Dict, List, Optional, Tuple

import requests

from app.models.tools.llm_interaction import LLMSettings
from app.models.tools.snomed_interaction import (
    SnomedCanonicalTerm,
    SnomedKeywordExpansionItem,
    SnomedMedicalKeywordItem,
    SnomedSettings,
    SnomedSynonym,
    SnomedVersionInfo,
)
from app.utils.llm_client import LLMClient
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

TRANSLATION_PROMPT = """Translate the following medical term from {source_language} to {target_language}.
Return only the translated term, without explanations or alternatives.

TERM:
{text}
"""

MEDICAL_KEYWORD_PROMPT = """You extract only concise medical keywords from German clinical text.

Keep only clinically meaningful terms such as:
- diagnoses, findings, symptoms, signs
- anatomy and body structures
- procedures, therapies, interventions
- imaging, tests, devices, substances, microorganisms

Do not include:
- boilerplate, discourse words, section labels
- generic verbs or abstract non-medical nouns
- long sentence fragments

Return ONLY a JSON array of unique strings in German, ordered from more specific to more general.
Limit to at most {max_keywords} items.

TEXT:
\"\"\"{text}\"\"\"
"""


class SnomedSynonymsCacheEntry:
    def __init__(
            self,
            *,
            queried_term: str,
            matched_term: Optional[str],
            canonical_form: Optional[str],
            concept_id: Optional[str],
            translated_via_llm: bool,
            synonyms: List[SnomedSynonym],
    ):
        self.queried_term = queried_term
        self.matched_term = matched_term
        self.canonical_form = canonical_form
        self.concept_id = concept_id
        self.translated_via_llm = translated_via_llm
        self.synonyms = synonyms


class SnomedService:
    def __init__(self):
        self.session = requests.Session()
        self._translation_cache: Dict[Tuple[str, str, str, str], str] = {}
        self._synonym_cache: Dict[Tuple[str, str, Optional[str], bool], SnomedSynonymsCacheEntry] = {}
        self._canonical_cache: Dict[Tuple[str, str, Optional[str], bool], SnomedCanonicalTerm] = {}
    
    @staticmethod
    def _normalize(text: str) -> str:
        text = re.sub(r"[\u2010-\u2015\-_/]", " ", text or "")
        return " ".join(text.lower().split())
    
    @staticmethod
    def _json_array(text: str) -> List[str]:
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except Exception:
            pass
        
        match = re.search(r"\[[\s\S]*\]", text or "")
        if not match:
            return []
        
        try:
            data = json.loads(match.group(0))
        except Exception:
            return []
        return [str(item).strip() for item in data if str(item).strip()]
    
    @staticmethod
    def _match_language(language_code: str, target_language: str) -> bool:
        return (language_code or "").lower().split("-")[0] == target_language.lower()
    
    @staticmethod
    def _settings_cache_key(term: str, settings: SnomedSettings, allow_english_fallback: bool) -> Tuple[str, str, Optional[str], bool]:
        return term.strip().lower(), settings.base_url.rstrip("/"), settings.version, allow_english_fallback
    
    def _translate(self, text: str, llm_settings: LLMSettings, source_language: str, target_language: str) -> str:
        cache_key = (
            text.strip(),
            source_language,
            target_language,
            llm_settings.model,
        )
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
        
        prompt = TRANSLATION_PROMPT.format(
            source_language=source_language,
            target_language=target_language,
            text=text.strip(),
        )
        translated = LLMClient(llm_settings).chat_text(prompt).strip()
        self._translation_cache[cache_key] = translated
        return translated
    
    def _expand(self, term: str, settings: SnomedSettings, display_language: str) -> Dict:
        params = {
            "url": settings.value_set_url,
            "filter": term,
            "count": str(settings.max_results),
            "includeDesignations": "true",
            "displayLanguage": display_language,
        }
        if settings.version:
            params["system-version"] = settings.version
        
        headers = {"Accept-Language": display_language, **settings.headers}
        response = self.session.get(
            f"{settings.base_url.rstrip('/')}/ValueSet/$expand",
            params=params,
            timeout=settings.timeout_s,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    def _get(self, path: str, settings: SnomedSettings, params: Optional[Dict[str, str]] = None) -> Dict:
        response = self.session.get(
            f"{settings.base_url.rstrip('/')}/{path.lstrip('/')}",
            params=params,
            timeout=settings.timeout_s,
            headers=settings.headers,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_versions_from_codesystem(bundle_json: Dict) -> List[SnomedVersionInfo]:
        entries = bundle_json.get("entry") or []
        versions: List[SnomedVersionInfo] = []
        seen = set()

        for entry in entries:
            resource = entry.get("resource") or {}
            version = (resource.get("version") or "").strip()
            if not version or version in seen:
                continue
            seen.add(version)
            versions.append(
                SnomedVersionInfo(
                    version=version,
                    title=(resource.get("title") or resource.get("name") or "").strip() or None,
                    url=(resource.get("url") or "").strip() or None,
                ),
            )

        return versions

    @staticmethod
    def _extract_versions_from_metadata(metadata_json: Dict) -> List[SnomedVersionInfo]:
        software_version = ((metadata_json.get("software") or {}).get("version") or "").strip()
        implementation_description = ((metadata_json.get("implementation") or {}).get("description") or "").strip()
        fhir_version = (metadata_json.get("fhirVersion") or "").strip()

        versions: List[SnomedVersionInfo] = []
        if software_version:
            versions.append(
                SnomedVersionInfo(
                    version=software_version,
                    title="Server software version",
                    url=None,
                ),
            )
        if fhir_version:
            versions.append(
                SnomedVersionInfo(
                    version=fhir_version,
                    title="FHIR version",
                    url=None,
                ),
            )
        if implementation_description and not versions:
            versions.append(
                SnomedVersionInfo(
                    version=implementation_description,
                    title="Implementation description",
                    url=None,
                ),
            )
        return versions

    def get_available_versions(self, settings: SnomedSettings) -> Tuple[str, List[SnomedVersionInfo]]:
        try:
            bundle_json = self._get("CodeSystem", settings, params={"url": "http://snomed.info/sct"})
            versions = self._extract_versions_from_codesystem(bundle_json)
            if versions:
                return "CodeSystem", versions
        except requests.RequestException:
            logger.exception("SNOMED CodeSystem version discovery failed")

        metadata_json = self._get("metadata", settings)
        versions = self._extract_versions_from_metadata(metadata_json)
        return "metadata", versions
    
    @staticmethod
    def _extract_first_match(expand_json: Dict, target_language: str) -> Tuple[Optional[str], Optional[str], List[SnomedSynonym]]:
        contains = (expand_json.get("expansion") or {}).get("contains") or []
        if not contains:
            return None, None, []
        
        top = contains[0]
        concept_id = top.get("code")
        display = (top.get("display") or "").strip() or None
        designations = top.get("designation") or []
        
        synonyms: List[SnomedSynonym] = []
        seen = set()
        
        if display:
            synonyms.append(SnomedSynonym(synonym=display, preference=1.0))
            seen.add(display.lower())
        
        for designation in designations:
            designation_type = ((designation.get("use") or {}).get("display") or "").strip().lower()
            language = (designation.get("language") or "").strip()
            value = (designation.get("value") or "").strip()
            if designation_type != "synonym" or not value:
                continue
            if not SnomedService._match_language(language, target_language):
                continue
            normalized = value.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            synonyms.append(SnomedSynonym(synonym=value, preference=1.0))
        
        return concept_id, display, synonyms
    
    def get_synonyms(
            self,
            term: str,
            *,
            llm_settings: LLMSettings,
            snomed_settings: SnomedSettings,
            allow_english_fallback: bool = True,
    ) -> SnomedSynonymsCacheEntry:
        cache_key = self._settings_cache_key(term, snomed_settings, allow_english_fallback)
        if cache_key in self._synonym_cache:
            return self._synonym_cache[cache_key]
        
        translated_via_llm = False
        matched_term = term.strip()
        
        try:
            expand_json = self._expand(term.strip(), snomed_settings, snomed_settings.display_language_de)
            concept_id, display, synonyms = self._extract_first_match(expand_json, target_language="de")
        except requests.RequestException:
            logger.exception("SNOMED synonym lookup failed for term '%s'", term)
            raise
        
        if not synonyms and allow_english_fallback:
            translated_term = self._translate(term.strip(), llm_settings, "German", "English").strip()
            if translated_term:
                translated_via_llm = True
                matched_term = translated_term
                expand_json = self._expand(translated_term, snomed_settings, snomed_settings.display_language_en)
                concept_id, display, synonyms = self._extract_first_match(expand_json, target_language="en")
                translated_synonyms: List[SnomedSynonym] = []
                seen = set()
                for synonym in synonyms:
                    translated = self._translate(synonym.synonym, llm_settings, "English", "German").strip()
                    if not translated:
                        continue
                    normalized = translated.lower()
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    translated_synonyms.append(SnomedSynonym(synonym=translated, preference=synonym.preference))
                synonyms = translated_synonyms
                if display:
                    display = self._translate(display, llm_settings, "English", "German").strip() or display
        
        result = SnomedSynonymsCacheEntry(
            queried_term=term.strip(),
            matched_term=matched_term,
            canonical_form=display,
            concept_id=concept_id,
            translated_via_llm=translated_via_llm,
            synonyms=synonyms,
        )
        self._synonym_cache[cache_key] = result
        return result
    
    def get_canonical_form(
            self,
            term: str,
            *,
            llm_settings: LLMSettings,
            snomed_settings: SnomedSettings,
            allow_english_fallback: bool = True,
    ) -> SnomedCanonicalTerm:
        cache_key = self._settings_cache_key(term, snomed_settings, allow_english_fallback)
        if cache_key in self._canonical_cache:
            return self._canonical_cache[cache_key]
        
        synonym_result = self.get_synonyms(
            term,
            llm_settings=llm_settings,
            snomed_settings=snomed_settings,
            allow_english_fallback=allow_english_fallback,
        )
        canonical = SnomedCanonicalTerm(
            queried_term=term.strip(),
            matched_term=synonym_result.matched_term,
            canonical_form=synonym_result.canonical_form,
            concept_id=synonym_result.concept_id,
            translated_via_llm=synonym_result.translated_via_llm,
        )
        self._canonical_cache[cache_key] = canonical
        return canonical
    
    def expand_keywords(
            self,
            keywords: List[str],
            *,
            llm_settings: LLMSettings,
            snomed_settings: SnomedSettings,
            allow_english_fallback: bool = True,
            include_original: bool = True,
    ) -> List[SnomedKeywordExpansionItem]:
        items: List[SnomedKeywordExpansionItem] = []
        
        for keyword in keywords:
            synonym_result = self.get_synonyms(
                keyword,
                llm_settings=llm_settings,
                snomed_settings=snomed_settings,
                allow_english_fallback=allow_english_fallback,
            )
            
            expanded_terms: List[str] = []
            seen = set()
            
            def add_term(value: Optional[str]) -> None:
                if not value:
                    return
                normalized = self._normalize(value)
                if normalized in seen:
                    return
                seen.add(normalized)
                expanded_terms.append(" ".join(value.split()))
            
            if include_original:
                add_term(keyword)
            add_term(synonym_result.canonical_form)
            for synonym in synonym_result.synonyms:
                add_term(synonym.synonym)
            
            items.append(
                SnomedKeywordExpansionItem(
                    keyword=keyword,
                    concept_id=synonym_result.concept_id,
                    canonical_form=synonym_result.canonical_form,
                    expanded_terms=expanded_terms,
                    translated_via_llm=synonym_result.translated_via_llm,
                ),
            )
        
        return items
    
    def extract_medical_keywords(
            self,
            text: str,
            *,
            llm_settings: LLMSettings,
            max_keywords: int = 20,
            snomed_settings: Optional[SnomedSettings] = None,
            resolve_canonical: bool = True,
            allow_english_fallback: bool = True,
    ) -> List[SnomedMedicalKeywordItem]:
        prompt = MEDICAL_KEYWORD_PROMPT.format(text=text.strip(), max_keywords=max_keywords)
        raw_keywords = self._json_array(LLMClient(llm_settings).chat_text(prompt))
        
        cleaned_keywords: List[str] = []
        seen = set()
        for keyword in raw_keywords:
            cleaned = " ".join(keyword.strip().rstrip(".,;:").split())
            if not cleaned:
                continue
            normalized = self._normalize(cleaned)
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned_keywords.append(cleaned)
        
        cleaned_keywords = cleaned_keywords[:max_keywords]
        results: List[SnomedMedicalKeywordItem] = []
        
        for keyword in cleaned_keywords:
            canonical_form = None
            concept_id = None
            translated_via_llm = False
            if snomed_settings is not None and resolve_canonical:
                canonical = self.get_canonical_form(
                    keyword,
                    llm_settings=llm_settings,
                    snomed_settings=snomed_settings,
                    allow_english_fallback=allow_english_fallback,
                )
                canonical_form = canonical.canonical_form
                concept_id = canonical.concept_id
                translated_via_llm = canonical.translated_via_llm
            
            results.append(
                SnomedMedicalKeywordItem(
                    keyword=keyword,
                    canonical_form=canonical_form,
                    concept_id=concept_id,
                    translated_via_llm=translated_via_llm,
                ),
            )
        
        return results
