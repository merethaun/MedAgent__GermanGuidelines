import json
import math
import re
import time
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Tuple

from app.models.knowledge.guideline.guideline_reference import GuidelineHierarchyEntry, GuidelineReference
from app.models.tools.guideline_context_filter import (
    GuidelineContextFilterDecision,
    GuidelineContextFilterKind,
    GuidelineContextFilterMethod,
    GuidelineContextFilterRequest,
    GuidelineContextFilterResponse,
    GuidelineContextFilterSettings,
    RetrievalPropertySelector,
)
from app.services.tools.llm_interaction_service import LLMInteractionService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

DEFAULT_LLM_FILTER_SYSTEM_PROMPT = """
You are a strict relevance judge for medical guideline retrieval.
For each item in REFERENCES, judge how useful it is for the FILTER_INPUT.

Relevance means usefulness for answering or supporting the FILTER_INPUT, not just keyword overlap.

Consider:
- topic match
- match to the specific clinical intent and constraints
- how much the item helps downstream answering

Scoring:
- 0.0 = irrelevant
- 0.1-0.3 = weakly related, not useful
- 0.4-0.6 = partially relevant, some useful information
- 0.7-0.8 = clearly relevant
- 0.9-1.0 = highly relevant and directly useful

Use conservative scoring for broad or vague matches.
Generic background should score low when the FILTER_INPUT is specific.
An item may still be relevant if it provides necessary supporting clinical context.

Return JSON only as an array with one object per item:
- index: integer
- keep: boolean
- score: number between 0 and 1
- reason: short explanation

Set keep=true when the item is sufficiently useful to retain.
""".strip()


class GuidelineContextFilterService:
    _cross_encoder_cache: Dict[str, Tuple[Any, Any]] = {}
    
    def __init__(self, llm_interaction_service: LLMInteractionService):
        self.llm_interaction_service = llm_interaction_service
    
    def filter_references(self, request: GuidelineContextFilterRequest) -> GuidelineContextFilterResponse:
        if request.settings.kind == GuidelineContextFilterKind.DEDUPLICATE:
            return self.deduplicate_references(request)
        if request.settings.kind == GuidelineContextFilterKind.RELEVANCE:
            return self.relevance_filter_references(request)
        raise ValueError(f"Unsupported filter kind: {request.settings.kind}")
    
    def deduplicate_references(self, request: GuidelineContextFilterRequest) -> GuidelineContextFilterResponse:
        started = time.time()
        settings = request.settings
        serialized_items = [self._serialize_reference(ref, settings) for ref in request.references]
        
        logger.debug(
            "GuidelineContextFilterService.deduplicate_references: references=%d strategy=%s properties=%s",
            len(request.references),
            settings.deduplicate_keep_strategy,
            [selector.path for selector in settings.properties],
        )
        
        decisions = self._deduplicate_filter(request.references, serialized_items, settings)
        kept_references, dropped_references, normalized_decisions = self._finalize(
            request.references,
            decisions,
            settings,
        )
        latency = time.time() - started
        
        logger.info(
            "Guideline deduplication completed: kept=%d dropped=%d latency=%.2fs",
            len(kept_references),
            len(dropped_references),
            latency,
        )
        
        return GuidelineContextFilterResponse(
            kind=settings.kind,
            method=settings.method,
            filter_input=request.filter_input,
            kept_references=kept_references,
            dropped_references=dropped_references,
            decisions=normalized_decisions,
            latency=latency,
        )
    
    def relevance_filter_references(self, request: GuidelineContextFilterRequest) -> GuidelineContextFilterResponse:
        started = time.time()
        settings = request.settings
        serialized_items = [self._serialize_reference(ref, settings) for ref in request.references]
        
        logger.debug(
            "GuidelineContextFilterService.relevance_filter_references: method=%s references=%d top_k=%s minimum_score=%s properties=%s",
            settings.method.value,
            len(request.references),
            settings.keep_top_k,
            settings.minimum_score,
            [selector.path for selector in settings.properties],
        )
        
        if settings.method == GuidelineContextFilterMethod.SCORE:
            decisions = self._score_filter(request.references, serialized_items, settings)
        elif settings.method == GuidelineContextFilterMethod.CROSS_ENCODER:
            decisions = self._cross_encoder_filter(request.filter_input, request.references, serialized_items, settings)
        elif settings.method == GuidelineContextFilterMethod.LLM:
            decisions = self._llm_filter(request.filter_input, request.references, serialized_items, settings)
        else:
            raise ValueError(f"Unsupported relevance filter method: {settings.method}")
        
        kept_references, dropped_references, normalized_decisions = self._finalize(
            request.references,
            decisions,
            settings,
        )
        latency = time.time() - started
        
        logger.info(
            "Guideline relevance filter completed: method=%s kept=%d dropped=%d latency=%.2fs",
            settings.method.value,
            len(kept_references),
            len(dropped_references),
            latency,
        )
        
        return GuidelineContextFilterResponse(
            kind=settings.kind,
            method=settings.method,
            filter_input=request.filter_input,
            kept_references=kept_references,
            dropped_references=dropped_references,
            decisions=normalized_decisions,
            latency=latency,
        )
    
    def _deduplicate_filter(
            self,
            references: List[GuidelineReference],
            serialized_items: List[str],
            settings: GuidelineContextFilterSettings,
    ) -> List[GuidelineContextFilterDecision]:
        grouped_indices: Dict[str, List[int]] = {}
        for index, serialized_item in enumerate(serialized_items):
            key = self._deduplicate_key(serialized_item, settings)
            grouped_indices.setdefault(key, []).append(index)
        
        kept_indices = set()
        for indices in grouped_indices.values():
            kept_indices.add(self._pick_deduplicated_index(indices, references, settings))
        
        decisions: List[GuidelineContextFilterDecision] = []
        for index, (reference, serialized_item) in enumerate(zip(references, serialized_items)):
            keep = index in kept_indices
            decisions.append(
                self._build_decision(
                    index=index,
                    reference=reference,
                    serialized_item=serialized_item,
                    score=self._coerce_float(self._resolve_value(reference, settings.score_field)),
                    kept=keep,
                    reason="Unique reference kept." if keep else "Duplicate reference removed.",
                ),
            )
        return decisions
    
    def _score_filter(
            self,
            references: List[GuidelineReference],
            serialized_items: List[str],
            settings: GuidelineContextFilterSettings,
    ) -> List[GuidelineContextFilterDecision]:
        return [
            self._build_decision(
                index=index,
                reference=reference,
                serialized_item=serialized_item,
                score=self._coerce_float(self._resolve_value(reference, settings.score_field)),
                kept=True,
                reason=f"Used numeric field '{settings.score_field}'.",
            )
            for index, (reference, serialized_item) in enumerate(zip(references, serialized_items))
        ]
    
    def _cross_encoder_filter(
            self,
            filter_input: str,
            references: List[GuidelineReference],
            serialized_items: List[str],
            settings: GuidelineContextFilterSettings,
    ) -> List[GuidelineContextFilterDecision]:
        try:
            import torch
            guard = torch.no_grad()
        except ModuleNotFoundError:
            guard = nullcontext()
        
        tokenizer, model = self._get_cross_encoder_bundle(settings.cross_encoder_model)
        encoded = tokenizer(
            [filter_input] * len(serialized_items),
            serialized_items,
            padding=True,
            truncation=True,
            max_length=settings.cross_encoder_max_length,
            return_tensors="pt",
        )
        
        with guard:
            logits = model(**encoded).logits
        
        scores = self._normalize_cross_encoder_logits(logits)
        return [
            self._build_decision(
                index=index,
                reference=reference,
                serialized_item=serialized_item,
                score=score,
                kept=True,
                reason=f"Cross-encoder score from '{settings.cross_encoder_model}'.",
            )
            for index, (reference, serialized_item, score) in enumerate(zip(references, serialized_items, scores))
        ]
    
    def _llm_filter(
            self,
            filter_input: str,
            references: List[GuidelineReference],
            serialized_items: List[str],
            settings: GuidelineContextFilterSettings,
    ) -> List[GuidelineContextFilterDecision]:
        prompt = self._build_llm_prompt(filter_input, serialized_items)
        raw_response = self.llm_interaction_service.generate_text(
            llm_settings=settings.llm_settings,
            system_prompt=settings.llm_system_prompt or DEFAULT_LLM_FILTER_SYSTEM_PROMPT,
            prompt=prompt,
        )
        raw_decisions = self._parse_llm_response(raw_response)
        decisions_by_index = {item["index"]: item for item in raw_decisions if "index" in item}
        
        return [
            self._build_decision(
                index=index,
                reference=reference,
                serialized_item=serialized_item,
                score=self._coerce_float(decisions_by_index.get(index, {}).get("score")),
                kept=bool(decisions_by_index.get(index, {}).get("keep", False)),
                reason=(decisions_by_index.get(index, {}).get("reason") or "No reason returned by LLM.").strip(),
            )
            for index, (reference, serialized_item) in enumerate(zip(references, serialized_items))
        ]
    
    @staticmethod
    def _finalize(
            references: List[GuidelineReference],
            decisions: List[GuidelineContextFilterDecision],
            settings: GuidelineContextFilterSettings,
    ) -> Tuple[List[GuidelineReference], List[GuidelineReference], List[GuidelineContextFilterDecision]]:
        indexed = list(enumerate(zip(references, decisions)))
        
        def passes_threshold(decision: GuidelineContextFilterDecision) -> bool:
            if not decision.kept:
                return False
            if settings.kind == GuidelineContextFilterKind.DEDUPLICATE:
                return decision.kept
            if settings.minimum_score is None or decision.score is None:
                return decision.kept
            return decision.score >= settings.minimum_score
        
        kept_pairs = [(index, reference, decision) for index, (reference, decision) in indexed if passes_threshold(decision)]
        dropped_pairs = [(index, reference, decision) for index, (reference, decision) in indexed if not passes_threshold(decision)]
        
        if settings.sort_by_score:
            kept_pairs.sort(key=lambda item: (math.inf if item[2].score is None else -item[2].score, item[0]))
        
        if settings.keep_top_k is not None:
            overflow = kept_pairs[settings.keep_top_k:]
            kept_pairs = kept_pairs[:settings.keep_top_k]
            for _, reference, decision in overflow:
                dropped_pairs.append(
                    (
                        decision.index,
                        reference,
                        decision.model_copy(update={"kept": False, "reason": (decision.reason or "") + " Cut by top-k."}),
                    ),
                )
        
        kept_references = [reference for _, reference, _ in kept_pairs]
        dropped_references = [reference for _, reference, _ in sorted(dropped_pairs, key=lambda item: item[0])]
        kept_indices = {decision.index for _, _, decision in kept_pairs}
        normalized_decisions = [
            decision.model_copy(update={"kept": decision.index in kept_indices})
            for _, (_, decision) in indexed
        ]
        return kept_references, dropped_references, normalized_decisions
    
    def _serialize_reference(self, reference: GuidelineReference, settings: GuidelineContextFilterSettings) -> str:
        parts: List[str] = []
        for selector in settings.properties:
            value = self._resolve_value(reference, selector.path)
            if value is None:
                if settings.include_empty_properties:
                    parts.append(self._format_property("", selector))
                continue
            
            text = str(value).strip()
            if not text and not settings.include_empty_properties:
                continue
            if selector.max_chars is not None:
                text = text[:selector.max_chars]
            parts.append(self._format_property(text, selector))
        return settings.joiner.join(parts).strip()
    
    @staticmethod
    def _deduplicate_key(serialized_item: str, settings: GuidelineContextFilterSettings) -> str:
        if not settings.deduplicate_use_normalized_text:
            return serialized_item
        return " ".join(serialized_item.lower().split())
    
    def _pick_deduplicated_index(
            self,
            indices: List[int],
            references: List[GuidelineReference],
            settings: GuidelineContextFilterSettings,
    ) -> int:
        if settings.deduplicate_keep_strategy == "first":
            return min(indices)
        
        def score_for(index: int) -> float:
            score = self._coerce_float(self._resolve_value(references[index], settings.score_field))
            return -math.inf if score is None else score
        
        return max(indices, key=lambda index: (score_for(index), -index))
    
    @staticmethod
    def _format_property(text: str, selector: RetrievalPropertySelector) -> str:
        label = selector.label or selector.path
        return f"{label}: {text}".strip() if selector.include_label else text
    
    @staticmethod
    def _resolve_value(reference: GuidelineReference, path: str) -> Any:
        if path == "content":
            return reference.extract_content()
        if path == "heading_path":
            return GuidelineContextFilterService._heading_path(reference)
        if path == "reference_id":
            return getattr(reference, "id", None)
        if hasattr(reference, path):
            return getattr(reference, path)
        
        current: Any = reference.model_dump()
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current
    
    @staticmethod
    def _heading_path(reference: GuidelineReference) -> str:
        parts: List[str] = []
        for entry in getattr(reference, "document_hierarchy", None) or []:
            if isinstance(entry, GuidelineHierarchyEntry):
                title = entry.title
            elif isinstance(entry, dict):
                title = entry.get("title")
            else:
                title = getattr(entry, "title", None)
            if title:
                parts.append(str(title))
        return " / ".join(parts)
    
    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    
    @classmethod
    def _get_cross_encoder_bundle(cls, model_name: str) -> Tuple[Any, Any]:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        
        cached = cls._cross_encoder_cache.get(model_name)
        if cached is not None:
            return cached
        
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        model.eval()
        cls._cross_encoder_cache[model_name] = (tokenizer, model)
        return tokenizer, model
    
    @staticmethod
    def _normalize_cross_encoder_logits(logits: Any) -> List[float]:
        import torch
        
        if logits.ndim == 1:
            return torch.sigmoid(logits).tolist()
        if logits.ndim == 2 and logits.shape[1] == 1:
            return torch.sigmoid(logits.squeeze(-1)).tolist()
        if logits.ndim == 2 and logits.shape[1] >= 2:
            return torch.softmax(logits, dim=1)[:, -1].tolist()
        raise ValueError(f"Unexpected cross-encoder logits shape: {tuple(logits.shape)}")
    
    @staticmethod
    def _build_llm_prompt(filter_input: str, serialized_items: List[str]) -> str:
        return (
                f"FILTER_INPUT:\n<<<\n{filter_input.strip()}\n>>>\n\n"
                "REFERENCES:\n"
                + json.dumps(
            [{"index": index, "reference": item} for index, item in enumerate(serialized_items)],
            ensure_ascii=False,
            indent=2,
        )
        )
    
    @staticmethod
    def _parse_llm_response(raw_response: str) -> List[Dict[str, Any]]:
        text = raw_response.strip()
        fence_match = re.search(r"```(?:json)?\s*(\[\s*[\s\S]*?\])\s*```", text, flags=re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1)
        elif not text.startswith("["):
            start = text.find("[")
            end = text.rfind("]")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("Could not parse JSON list from LLM filter response.")
            text = text[start:end + 1]
        
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("LLM filter response must be a JSON list.")
        return [item for item in parsed if isinstance(item, dict)]
    
    @staticmethod
    def _build_decision(
            *,
            index: int,
            reference: GuidelineReference,
            serialized_item: str,
            score: Optional[float],
            kept: bool,
            reason: str,
    ) -> GuidelineContextFilterDecision:
        return GuidelineContextFilterDecision(
            index=index,
            kept=kept,
            score=score,
            reason=reason,
            serialized_item=serialized_item,
            reference_id=str(reference.id) if getattr(reference, "id", None) is not None else None,
            source_id=str(reference.guideline_id) if getattr(reference, "guideline_id", None) is not None else None,
        )
