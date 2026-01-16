from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.knowledge.guidelines.keyword_models import ExtractKeywordsRequest
from app.services.knowledge.guidelines.keywords.keyword_service import KeywordService
from app.utils.logger import setup_logger
from app.utils.service_creators import get_keyword_service

logger = setup_logger(__name__)
keyword_router = APIRouter()


@keyword_router.post("/extract", response_model=List[str], status_code=status.HTTP_200_OK)
def extract_keywords(
        payload: ExtractKeywordsRequest,
        service: KeywordService = Depends(get_keyword_service),
):
    """
    Extract keywords from text using YAKE or an LLM (via LlamaIndex).
    - method='yake' → uses YAKE path
    - method='llm'  → uses LLM path with optional settings in `llm`
    """
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="The 'text' field must not be empty.")
    
    if payload.method == "yake":
        # LLM path
        if payload.yake is None:
            raise HTTPException(status_code=400, detail="yake settings are required when method='yake'.")
        
        yake = payload.yake
        try:
            keywords = service.extract_yake(
                text, min_keywords=yake.min_keywords, max_keywords=yake.max_keywords, ignore_terms=yake.ignore_terms,
                language=yake.language, max_n_gram_size=yake.max_n_gram_size,
                deduplication_threshold=yake.deduplication_threshold,
            )
            return keywords
        except Exception as e:
            logger.error(f"YAKE extraction failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"YAKE extraction failed: {e}")
    elif payload.method == "llm":
        # LLM path
        if payload.llm is None:
            raise HTTPException(status_code=400, detail="llm settings are required when method='llm'.")
        
        llm = payload.llm
        try:
            keywords = service.extract_llm(
                text=text, model=llm.model, api_key=llm.api_key, api_base=llm.api_base, temperature=llm.temperature, max_tokens=llm.max_tokens,
                scope_description=llm.scope_description, guidance_additions=llm.guidance_additions, ignore_terms=llm.ignore_terms,
                important_terms=llm.important_terms, examples=llm.examples, min_keywords=llm.min_keywords, max_keywords=llm.max_keywords,
            )
            return keywords
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"LLM extraction failed: {e}")
    else:
        logger.error(f"Invalid method: {payload.method}")
        raise HTTPException(status_code=400, detail="Invalid method. Must be one of 'yake' or 'llm'.")
