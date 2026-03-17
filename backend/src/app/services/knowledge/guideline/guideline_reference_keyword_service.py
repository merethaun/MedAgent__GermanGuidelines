from dataclasses import dataclass
from typing import Any, List

from app.models.knowledge.guideline import (
    GuidelineReference,
    ReferenceKeywordEnrichmentItem,
    ReferenceKeywordEnrichmentRequest,
    ReferenceKeywordEnrichmentResult,
)
from app.services.tools import KeywordService, SnomedService


@dataclass
class GuidelineReferenceKeywordService:
    reference_service: Any
    keyword_service: KeywordService
    snomed_service: SnomedService
    
    def enrich_keywords(self, request: ReferenceKeywordEnrichmentRequest) -> ReferenceKeywordEnrichmentResult:
        references = self._load_references(request)
        
        results: List[ReferenceKeywordEnrichmentItem] = []
        skipped_reference_ids: List[str] = []
        
        for reference in references:
            content = (reference.extract_content() or "").strip()
            if not content:
                skipped_reference_ids.append(str(reference.id))
                continue
            
            extracted_keywords = self._extract_keywords(reference, content, request)
            if not extracted_keywords:
                skipped_reference_ids.append(str(reference.id))
                continue
            
            stored_keywords = self._expand_keywords_if_needed(extracted_keywords, request)
            if not request.replace_existing and reference.associated_keywords:
                stored_keywords = self._deduplicate_keywords(reference.associated_keywords + stored_keywords)
            
            updated = self.reference_service.update_reference(
                reference.id,
                {"associated_keywords": stored_keywords},
            )
            
            results.append(
                ReferenceKeywordEnrichmentItem(
                    reference_id=updated.id,
                    extracted_keywords=extracted_keywords,
                    stored_keywords=stored_keywords,
                ),
            )
        
        return ReferenceKeywordEnrichmentResult(
            processed_reference_count=len(results),
            skipped_reference_ids=skipped_reference_ids,
            references=results,
        )
    
    def _load_references(self, request: ReferenceKeywordEnrichmentRequest) -> List[GuidelineReference]:
        if request.reference_id is not None:
            return [self.reference_service.get_reference_by_id(request.reference_id)]
        
        return self.reference_service.list_references(
            reference_group_id=request.reference_group_id,
            guideline_id=request.guideline_id,
        )
    
    def _extract_keywords(
            self,
            reference: GuidelineReference,
            content: str,
            request: ReferenceKeywordEnrichmentRequest,
    ) -> List[str]:
        settings = request.keyword_settings
        
        if settings.strategy.value == "yake":
            keywords = self.keyword_service.extract_yake(
                text=content,
                language=settings.language,
                min_keywords=settings.min_keywords,
                max_keywords=settings.max_keywords,
                max_n_gram_size=settings.max_n_gram_size,
                deduplication_threshold=settings.deduplication_threshold,
                ignore_terms=settings.ignore_terms,
                suppress_subphrases=settings.suppress_subphrases,
                headroom=settings.headroom,
            )
        else:
            if settings.llm_settings is None:
                raise ValueError("keyword_settings.llm_settings is required for strategy='llm'.")
            keywords = self.keyword_service.extract_llm(
                content,
                llm_settings=settings.llm_settings,
                scope_description=settings.scope_description,
                guidance_additions=settings.guidance_additions,
                ignore_terms=settings.ignore_terms,
                important_terms=settings.important_terms,
                examples=settings.examples,
                min_keywords=settings.min_keywords,
                max_keywords=settings.max_keywords,
            )
        
        return self._deduplicate_keywords(keywords)
    
    def _expand_keywords_if_needed(
            self,
            extracted_keywords: List[str],
            request: ReferenceKeywordEnrichmentRequest,
    ) -> List[str]:
        if not request.expansion_settings.enabled:
            return extracted_keywords
        
        llm_settings = request.keyword_settings.llm_settings
        if llm_settings is None:
            raise ValueError("keyword_settings.llm_settings is required when SNOMED expansion is enabled.")
        
        items = self.snomed_service.expand_keywords(
            extracted_keywords,
            llm_settings=llm_settings,
            snomed_settings=request.expansion_settings.snomed_settings,
            allow_english_fallback=request.expansion_settings.allow_english_fallback,
            include_original=request.expansion_settings.include_original,
        )
        
        expanded_keywords: List[str] = []
        for item in items:
            expanded_keywords.extend(item.expanded_terms)
        return self._deduplicate_keywords(expanded_keywords)
    
    @staticmethod
    def _deduplicate_keywords(keywords: List[str]) -> List[str]:
        seen = set()
        deduplicated: List[str] = []
        for keyword in keywords:
            cleaned = " ".join((keyword or "").split())
            if not cleaned:
                continue
            normalized = cleaned.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduplicated.append(cleaned)
        return deduplicated
