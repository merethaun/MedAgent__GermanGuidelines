from dataclasses import dataclass

from typing import Literal, List, Optional, Union


@dataclass
class RetrieveSettings:
    queries: List[str]
    top_k: int = 10
    context_size_c: int = 3


@dataclass
class FilterSettings:
    option: Literal["query", "generation_based"]
    query: Optional[str] = None
    threshold_query_relevance: Optional[float] = None
    gen_result: Optional[str] = None


@dataclass
class GenerateSettings:
    additional_comment: Optional[str] = None


@dataclass
class RAGAsResult:
    question_answered: float
    response_relevance: float
    context_relevance: float
    response_groundedness: float
    faithfulness: Optional[float]


@dataclass
class Action:
    action_type: Literal["retrieve", "filter", "generate", "end"]
    settings: Union[RetrieveSettings, FilterSettings, GenerateSettings, None]
    score: Optional[RAGAsResult] = None
