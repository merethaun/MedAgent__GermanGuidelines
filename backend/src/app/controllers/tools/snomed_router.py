from fastapi import APIRouter, Depends, HTTPException, status

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import require_roles
from app.models.tools.snomed_interaction import (
    SnomedCanonicalTerm,
    SnomedKeywordExpansionRequest,
    SnomedKeywordExpansionResponse,
    SnomedMedicalKeywordRequest,
    SnomedMedicalKeywordResponse,
    SnomedSynonymsResponse,
    SnomedTermRequest,
    SnomedVersionsRequest,
    SnomedVersionsResponse,
)
from app.services.service_registry import get_snomed_service
from app.services.tools import SnomedService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

snomed_router = APIRouter()


@snomed_router.post(
    "/snomed/versions",
    response_model=SnomedVersionsResponse,
    status_code=status.HTTP_200_OK,
    summary="List SNOMED versions available on the configured server (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def get_snomed_versions(
        req: SnomedVersionsRequest,
        service: SnomedService = Depends(get_snomed_service),
) -> SnomedVersionsResponse:
    try:
        source, versions = service.get_available_versions(req.snomed_settings)
        return SnomedVersionsResponse(versions=versions, source=source)
    except Exception as e:
        logger.error("SNOMED version discovery failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@snomed_router.post(
    "/snomed/synonyms",
    response_model=SnomedSynonymsResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve SNOMED synonyms for a term (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def get_snomed_synonyms(
        req: SnomedTermRequest,
        service: SnomedService = Depends(get_snomed_service),
) -> SnomedSynonymsResponse:
    try:
        result = service.get_synonyms(
            req.term,
            llm_settings=req.llm_settings,
            snomed_settings=req.snomed_settings,
            allow_english_fallback=req.allow_english_fallback,
        )
        return SnomedSynonymsResponse(
            queried_term=result.queried_term,
            matched_term=result.matched_term,
            canonical_form=result.canonical_form,
            concept_id=result.concept_id,
            translated_via_llm=result.translated_via_llm,
            synonyms=result.synonyms,
        )
    except Exception as e:
        logger.error("SNOMED synonym lookup failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@snomed_router.post(
    "/snomed/canonical",
    response_model=SnomedCanonicalTerm,
    status_code=status.HTTP_200_OK,
    summary="Resolve the canonical SNOMED form for a term (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def get_snomed_canonical(
        req: SnomedTermRequest,
        service: SnomedService = Depends(get_snomed_service),
) -> SnomedCanonicalTerm:
    try:
        return service.get_canonical_form(
            req.term,
            llm_settings=req.llm_settings,
            snomed_settings=req.snomed_settings,
            allow_english_fallback=req.allow_english_fallback,
        )
    except Exception as e:
        logger.error("SNOMED canonical lookup failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@snomed_router.post(
    "/snomed/expand",
    response_model=SnomedKeywordExpansionResponse,
    status_code=status.HTTP_200_OK,
    summary="Expand keywords with SNOMED synonyms (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def expand_snomed_keywords(
        req: SnomedKeywordExpansionRequest,
        service: SnomedService = Depends(get_snomed_service),
) -> SnomedKeywordExpansionResponse:
    try:
        items = service.expand_keywords(
            req.keywords,
            llm_settings=req.llm_settings,
            snomed_settings=req.snomed_settings,
            allow_english_fallback=req.allow_english_fallback,
            include_original=req.include_original,
        )
        expanded_keywords = []
        seen = set()
        for item in items:
            for term in item.expanded_terms:
                normalized = " ".join(term.lower().split())
                if normalized in seen:
                    continue
                seen.add(normalized)
                expanded_keywords.append(term)
        return SnomedKeywordExpansionResponse(expanded_keywords=expanded_keywords, items=items)
    except Exception as e:
        logger.error("SNOMED keyword expansion failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@snomed_router.post(
    "/snomed/medical-keywords",
    response_model=SnomedMedicalKeywordResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract medical keywords from text (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def extract_snomed_medical_keywords(
        req: SnomedMedicalKeywordRequest,
        service: SnomedService = Depends(get_snomed_service),
) -> SnomedMedicalKeywordResponse:
    try:
        keywords = service.extract_medical_keywords(
            req.text,
            llm_settings=req.llm_settings,
            max_keywords=req.max_keywords,
            snomed_settings=req.snomed_settings,
            resolve_canonical=req.resolve_canonical,
            allow_english_fallback=req.allow_english_fallback,
        )
        return SnomedMedicalKeywordResponse(keywords=keywords)
    except Exception as e:
        logger.error("SNOMED medical keyword extraction failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
