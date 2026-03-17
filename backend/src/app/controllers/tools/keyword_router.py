from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import require_roles
from app.models.tools.keyword_interaction import KeywordBothResponse, KeywordExtractionResponse, KeywordLLMRequest, KeywordYakeRequest
from app.models.tools.llm_interaction import LLMSettings
from app.services.service_registry import get_keyword_service
from app.services.tools import KeywordService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

keyword_router = APIRouter()


@keyword_router.get(
    "/keywords/defaults",
    response_model=Dict[str, Any],
    summary="Get keyword extraction defaults (admin only)",
    description="Returns DEFAULT_KEYWORD_SETTINGS and prompt template info for debugging.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def get_keyword_defaults() -> Dict[str, Any]:
    try:
        from app.services.tools.keyword_service import DEFAULT_KEYWORD_SETTINGS, KEYWORDS_PROMPT  # noqa
        
        return {
            "DEFAULT_KEYWORD_SETTINGS": DEFAULT_KEYWORD_SETTINGS,
            "KEYWORDS_PROMPT_preview": KEYWORDS_PROMPT[:500] + " ...",
        }
    except Exception as e:
        logger.error("Failed to return keyword defaults: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@keyword_router.post(
    "/keywords/yake",
    response_model=KeywordExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract keywords via YAKE (admin only)",
    description="Runs KeywordService.extract_yake() on the provided text.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def extract_keywords_yake(
        req: KeywordYakeRequest,
        service: KeywordService = Depends(get_keyword_service),
) -> KeywordExtractionResponse:
    try:
        logger.info("Tools/Keywords YAKE: text_len=%d lang=%s", len(req.text), req.language)
        
        keywords = service.extract_yake(
            text=req.text,
            language=req.language,
            min_keywords=req.min_keywords,
            max_keywords=req.max_keywords,
            max_n_gram_size=req.max_n_gram_size,
            deduplication_threshold=req.deduplication_threshold,
            ignore_terms=req.ignore_terms,
            suppress_subphrases=req.suppress_subphrases,
            headroom=req.headroom,
        )
        
        return KeywordExtractionResponse(keywords=keywords)
    
    except Exception as e:
        logger.error("YAKE keyword extraction failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@keyword_router.post(
    "/keywords/llm",
    response_model=KeywordExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract keywords via LLM (admin only)",
    description="Runs KeywordService.extract_llm() on the provided text and LLM settings.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def extract_keywords_llm(
        req: KeywordLLMRequest,
        service: KeywordService = Depends(get_keyword_service),
) -> KeywordExtractionResponse:
    try:
        logger.info(
            "Tools/Keywords LLM: text_len=%d model=%s base_url=%s",
            len(req.text),
            getattr(req.llm_settings, "model", None),
            getattr(req.llm_settings, "base_url", None),
        )
        
        keywords = service.extract_llm(
            req.text,
            llm_settings=req.llm_settings,
            scope_description=req.scope_description,
            guidance_additions=req.guidance_additions,
            ignore_terms=req.ignore_terms,
            important_terms=req.important_terms,
            examples=req.examples,
            min_keywords=req.min_keywords,
            max_keywords=req.max_keywords,
        )
        
        return KeywordExtractionResponse(keywords=keywords)
    
    except Exception as e:
        logger.error("LLM keyword extraction failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@keyword_router.post(
    "/keywords/both",
    response_model=KeywordBothResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract keywords via YAKE + LLM (admin only)",
    description="Runs both extractors and returns both lists plus overlap/union.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def extract_keywords_both(
        text: str = Query(..., description="Input text passage"),
        language: str = Query("de", description="YAKE language code"),
        min_keywords: Optional[int] = Query(None, ge=1, description="Minimum desired keywords"),
        max_keywords: Optional[int] = Query(None, ge=1, description="Maximum desired keywords"),
        llm_settings: LLMSettings = Depends(),
        service: KeywordService = Depends(get_keyword_service),
) -> KeywordBothResponse:
    try:
        logger.info("Tools/Keywords BOTH: text_len=%d lang=%s", len(text), language)
        
        yake_kw = service.extract_yake(
            text=text,
            language=language,
            min_keywords=min_keywords,
            max_keywords=max_keywords,
        )
        
        llm_kw = service.extract_llm(
            text,
            llm_settings=llm_settings,
            min_keywords=min_keywords,
            max_keywords=max_keywords,
        )
        
        overlap = sorted(set(yake_kw).intersection(set(llm_kw)))
        union = sorted(set(yake_kw).union(set(llm_kw)))
        
        return KeywordBothResponse(yake=yake_kw, llm=llm_kw, overlap=overlap, union=union)
    
    except Exception as e:
        logger.error("BOTH keyword extraction failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
