import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

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
        expected = [
            normalized_text
            for normalized_text in (self._normalize_text(snippet.retrieval_text) for snippet in sample.expected_retrieval)
            if normalized_text
        ]
        actual = [
            normalized_text
            for normalized_text in (
                self._normalize_text(self._extract_retrieval_text(item)) for item in sample.retrieval_output
            )
            if normalized_text
        ]
        if not expected:
            return RetrievalMetrics(retrieval_latency=sample.retrieval_latency)

        tp_strings, fn_strings, fp_strings = self._get_tp_fp_fn_strings(expected.copy(), actual.copy())
        tp = sum(self._string_to_unit_count(text) for text in tp_strings)
        fn = sum(self._string_to_unit_count(text) for text in fn_strings)
        fp = sum(self._string_to_unit_count(text) for text in fp_strings)

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
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
        for key in (
                "contained_text",
                "recommendation_content",
                "statement_content",
                "metadata_content",
                "plain_text",
                "table_markdown",
                "describing_text",
                "caption",
        ):
            if properties.get(key):
                return str(properties[key])
        return ""

    @staticmethod
    def _string_to_unit_count(text: str) -> int:
        return len("".join(text.split()))

    @staticmethod
    def _get_tp_fp_fn_strings(
            expected_retrieval_texts: List[str],
            actual_retrieval_texts: List[str],
    ) -> Tuple[List[str], List[str], List[str]]:
        def get_lcs(left: str, right: str) -> Optional[str]:
            matcher = SequenceMatcher(None, left, right)
            match = matcher.find_longest_match(0, len(left), 0, len(right))
            if match.size == 0:
                return None
            longest_common_substring = left[match.a:match.a + match.size]
            if not longest_common_substring.strip():
                return None
            return longest_common_substring

        def split_once(text: str, substring: str) -> Tuple[str, str]:
            before, _, after = text.partition(substring)
            return before, after

        tp_strings: List[str] = []
        expected_index = 0
        while expected_index < len(expected_retrieval_texts):
            expected_text = expected_retrieval_texts[expected_index]
            actual_index = 0
            while actual_index < len(actual_retrieval_texts):
                actual_text = actual_retrieval_texts[actual_index]
                longest_common_substring = get_lcs(expected_text, actual_text)
                if longest_common_substring is None:
                    actual_index += 1
                    continue

                if actual_text == longest_common_substring:
                    tp_strings.append(actual_text)
                    actual_retrieval_texts[actual_index] = ""
                    left_text, right_text = split_once(expected_text, actual_text)
                    expected_retrieval_texts[expected_index] = left_text
                    expected_retrieval_texts.insert(expected_index + 1, right_text)
                elif expected_text == longest_common_substring:
                    tp_strings.append(expected_text)
                    expected_retrieval_texts[expected_index] = ""
                    left_text, right_text = split_once(actual_text, expected_text)
                    actual_retrieval_texts[actual_index] = left_text
                    actual_retrieval_texts.insert(actual_index + 1, right_text)
                elif actual_text.startswith(longest_common_substring) and expected_text.endswith(longest_common_substring):
                    tp_strings.append(longest_common_substring)
                    expected_retrieval_texts[expected_index] = expected_text[:-len(longest_common_substring)]
                    actual_retrieval_texts[actual_index] = actual_text[len(longest_common_substring):]
                elif actual_text.endswith(longest_common_substring) and expected_text.startswith(longest_common_substring):
                    tp_strings.append(longest_common_substring)
                    expected_retrieval_texts[expected_index] = expected_text[len(longest_common_substring):]
                    actual_retrieval_texts[actual_index] = actual_text[:-len(longest_common_substring)]

                actual_index += 1

            expected_index += 1

        fp_strings = [text for text in actual_retrieval_texts if text]
        fn_strings = [text for text in expected_retrieval_texts if text]
        return tp_strings, fn_strings, fp_strings

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
