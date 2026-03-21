from typing import Optional

from pydantic import BaseModel


class RetrievalMetrics(BaseModel):
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    retrieval_latency: Optional[float] = None


class LexicalMetrics(BaseModel):
    exact_match: Optional[float] = None
    token_f1: Optional[float] = None
    jaccard: Optional[float] = None
    sequence_ratio: Optional[float] = None


class EmbeddingMetrics(BaseModel):
    provider: Optional[str] = None
    cosine_similarity: Optional[float] = None
    euclidean_distance: Optional[float] = None
    status: Optional[str] = None
    note: Optional[str] = None


class GPTScoreMetrics(BaseModel):
    similarity: Optional[float] = None
    reasoning: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None


class AutomaticMetrics(BaseModel):
    response_latency: Optional[float] = None
    retrieval: RetrievalMetrics = RetrievalMetrics()
    lexical: Optional[LexicalMetrics] = None
    embeddings: Optional[EmbeddingMetrics] = None
    gpt_score: Optional[GPTScoreMetrics] = None
