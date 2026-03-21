import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from app.models.evaluation.metrics import AutomaticMetrics, EmbeddingMetrics, GPTScoreMetrics, LexicalMetrics, RetrievalMetrics
from app.models.evaluation.run import EvaluationSample
from app.services.backend_api_client import BackendApiClient
from app.services.evaluation.prompt_loader import PromptLoader


@dataclass
class MetricService:
    backend_client: BackendApiClient
    prompt_loader: PromptLoader

    def compute_for_sample(
            self,
            sample: EvaluationSample,
            access_token: str,
            llm_settings_override: Optional[Dict[str, Any]] = None,
    ) -> AutomaticMetrics:
        metrics = AutomaticMetrics(response_latency=sample.response_latency)
        metrics.retrieval = self._compute_retrieval_metrics(sample)
        if sample.expected_answer:
            metrics.lexical = self._compute_lexical_metrics(sample.expected_answer, sample.answer_text or "")
            metrics.embeddings = self._compute_embedding_metrics(sample.expected_answer, sample.answer_text or "", access_token)
            metrics.gpt_score = self._compute_gpt_score(sample, access_token, llm_settings_override=llm_settings_override)
        return metrics

    def _compute_retrieval_metrics(self, sample: EvaluationSample) -> RetrievalMetrics:
        expected = [self._normalize_text(snippet.retrieval_text) for snippet in sample.expected_retrieval if snippet.retrieval_text]
        actual = [self._normalize_text(self._extract_retrieval_text(item)) for item in sample.retrieval_output if self._extract_retrieval_text(item)]
        if not expected:
            return RetrievalMetrics(retrieval_latency=sample.retrieval_latency)

        matched_expected = sum(
            1
            for expected_item in expected
            if any(expected_item and (expected_item in actual_item or actual_item in expected_item) for actual_item in actual)
        )
        matched_actual = sum(
            1
            for actual_item in actual
            if any(actual_item and (actual_item in expected_item or expected_item in actual_item) for expected_item in expected)
        )

        precision = matched_actual / len(actual) if actual else 0.0
        recall = matched_expected / len(expected) if expected else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        return RetrievalMetrics(precision=precision, recall=recall, f1=f1, retrieval_latency=sample.retrieval_latency)

    def _compute_lexical_metrics(self, expected: str, actual: str) -> LexicalMetrics:
        norm_expected = self._normalize_text(expected)
        norm_actual = self._normalize_text(actual)
        expected_tokens = self._tokenize(norm_expected)
        actual_tokens = self._tokenize(norm_actual)

        exact_match = 1.0 if norm_expected == norm_actual and norm_expected else 0.0
        overlap = Counter(expected_tokens) & Counter(actual_tokens)
        shared = sum(overlap.values())
        precision = shared / len(actual_tokens) if actual_tokens else 0.0
        recall = shared / len(expected_tokens) if expected_tokens else 0.0
        token_f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        union = set(expected_tokens) | set(actual_tokens)
        jaccard = len(set(expected_tokens) & set(actual_tokens)) / len(union) if union else 0.0
        sequence_ratio = SequenceMatcher(None, norm_expected, norm_actual).ratio() if norm_expected or norm_actual else 0.0

        return LexicalMetrics(
            exact_match=exact_match,
            token_f1=token_f1,
            jaccard=jaccard,
            sequence_ratio=sequence_ratio,
        )

    def _compute_embedding_metrics(self, expected: str, actual: str, access_token: str) -> EmbeddingMetrics:
        try:
            response = self.backend_client.embed_texts([expected, actual], access_token)
            embeddings = response.get("embeddings") or []
            if len(embeddings) != 2:
                raise RuntimeError("Expected two embeddings for embedding metric computation")
            cosine_similarity = self._cosine_similarity(embeddings[0], embeddings[1])
            euclidean_distance = self._euclidean_distance(embeddings[0], embeddings[1])
            return EmbeddingMetrics(
                provider=response.get("provider"),
                cosine_similarity=cosine_similarity,
                euclidean_distance=euclidean_distance,
                status="ok",
            )
        except Exception as exc:
            return EmbeddingMetrics(status="unavailable", note=str(exc))

    def _compute_gpt_score(
            self,
            sample: EvaluationSample,
            access_token: str,
            llm_settings_override: Optional[Dict[str, Any]] = None,
    ) -> GPTScoreMetrics:
        system_prompt = "\n\n".join(
            [
                self.prompt_loader.load_gptscore_prompt(),
                self.prompt_loader.load_gptscore_examples(),
            ],
        )
        user_prompt = json.dumps(
            {
                "question": sample.question_text,
                "expected_answer": sample.expected_answer,
                "actual_answer": sample.answer_text,
                "expected_retrieval": [snippet.model_dump() for snippet in sample.expected_retrieval],
                "actual_retrieval": sample.retrieval_output,
            },
            ensure_ascii=False,
        )
        try:
            raw = self.backend_client.run_gpt_score(
                system_prompt,
                user_prompt,
                access_token,
                runtime_llm_settings=llm_settings_override,
            ) or ""
            parsed = self._parse_json_object(raw)
            similarity = parsed.get("similarity")
            similarity_value = None if similarity is None else float(similarity)
            return GPTScoreMetrics(similarity=similarity_value, reasoning=parsed.get("reasoning"), status="ok")
        except Exception as exc:
            return GPTScoreMetrics(status="unavailable", note=str(exc))

    @staticmethod
    def _extract_retrieval_text(item: Dict[str, Any]) -> str:
        if item.get("retrieval"):
            return str(item["retrieval"])
        properties = item.get("weaviate_properties") or {}
        for key in ("contained_text", "recommendation_content", "statement_content", "caption", "plain_text"):
            if properties.get(key):
                return str(properties[key])
        return ""

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^0-9A-Za-zÄÖÜäöüß]+", " ", (text or "").lower())).strip()

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [token for token in text.split(" ") if token]

    @staticmethod
    def _cosine_similarity(left: List[float], right: List[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _euclidean_distance(left: List[float], right: List[float]) -> float:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))

    @staticmethod
    def _parse_json_object(raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))
