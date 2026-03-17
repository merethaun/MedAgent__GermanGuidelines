import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List

from app.models.tools.llm_interaction import LLMSettings
from app.services.tools.llm_interaction_service import LLMInteractionService


@dataclass
class QueryRewriteResult:
    query: str
    system_prompt: str
    prompt: str
    full_response: str
    rewritten_query: str
    session_id: str


@dataclass
class HyDEQueryResult:
    query: str
    system_prompt: str
    prompt: str
    full_response: str
    documents: List[str]
    session_id: str


@dataclass
class QueryMergeResult:
    query: str
    system_prompt: str
    prompt: str
    full_response: str
    merged_query: str


class QueryTransformationService:
    def __init__(self, llm_interaction_service: LLMInteractionService):
        self.llm_interaction_service = llm_interaction_service
    
    def rewrite_query(
            self,
            *,
            query: str,
            system_prompt: str,
            prompt: str,
            llm_settings: LLMSettings,
            session_id: str,
    ) -> QueryRewriteResult:
        full_response = self.llm_interaction_service.generate_text(
            llm_settings=llm_settings,
            prompt=prompt,
            system_prompt=system_prompt,
            session_id=session_id,
        )
        return QueryRewriteResult(
            query=query,
            system_prompt=system_prompt,
            prompt=prompt,
            full_response=full_response,
            rewritten_query=(full_response or "").strip(),
            session_id=session_id,
        )
    
    def generate_hyde_documents(
            self,
            *,
            query: str,
            system_prompt: str,
            prompt: str,
            llm_settings: LLMSettings,
            session_id: str,
            min_chars: int,
            max_similarity: float,
    ) -> HyDEQueryResult:
        full_response = self.llm_interaction_service.generate_text(
            llm_settings=llm_settings,
            prompt=prompt,
            system_prompt=system_prompt,
            session_id=session_id,
        )
        documents = self._filter_documents(
            self._extract_documents(full_response),
            min_chars=min_chars,
            max_similarity=max_similarity,
        )
        return HyDEQueryResult(
            query=query,
            system_prompt=system_prompt,
            prompt=prompt,
            full_response=full_response,
            documents=documents,
            session_id=session_id,
        )
    
    def merge_query_with_history(
            self,
            *,
            query: str,
            system_prompt: str,
            prompt: str,
            llm_settings: LLMSettings,
    ) -> QueryMergeResult:
        full_response = self.llm_interaction_service.generate_text(
            llm_settings=llm_settings,
            prompt=prompt,
            system_prompt=system_prompt,
        )
        merged_query = (full_response or "").strip() or query.strip()
        return QueryMergeResult(
            query=query,
            system_prompt=system_prompt,
            prompt=prompt,
            full_response=full_response,
            merged_query=merged_query,
        )
    
    @staticmethod
    def _extract_documents(raw_text: str) -> List[str]:
        matches = re.findall(r"<document>\s*(.*?)\s*</document>", raw_text or "", flags=re.IGNORECASE | re.DOTALL)
        return [match.strip() for match in matches if str(match).strip()]
    
    @staticmethod
    def _filter_documents(documents: List[str], *, min_chars: int, max_similarity: float) -> List[str]:
        filtered: List[str] = []
        for document in documents:
            if len(document.strip()) < int(min_chars):
                continue
            
            normalized = " ".join(document.lower().split())
            is_duplicate = any(
                SequenceMatcher(a=normalized, b=" ".join(existing.lower().split())).ratio() > float(max_similarity)
                for existing in filtered
            )
            if not is_duplicate:
                filtered.append(document)
        return filtered
