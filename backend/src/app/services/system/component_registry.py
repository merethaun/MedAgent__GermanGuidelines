from app.services.system.components import AbstractComponent
from app.services.system.components.complex_pattern.adaptive import (
    ActionTrackerComponent, AdaptDecisionComponent, RetrieveActionComponent, FilterActionComponent,
)
from app.services.system.components.complex_pattern.judge import AbstractJudge, RAGAsJudge, QuestionInScopeJudge
from app.services.system.components.complex_pattern.question_decomposition import (
    AbstractDecomposeComponent, SplitComponent, MergeComponent,
    DecomposeSplitAzureOpenAIGenerator, DecomposeSplitOllamaGenerator, DecomposeMergeAzureOpenAIGenerator, DecomposeMergeOllamaGenerator,
)
from app.services.system.components.generator import AbstractGenerator, AzureOpenAIGenerator, OllamaGenerator
from app.services.system.components.generator.hyde import AbstractHyDEGenerator, HyDEOllamaGenerator, HyDEAzureOpenAIGenerator
from app.services.system.components.generator.keyword import AbstractKeywordExtractor, LLMKeywordExtractor, YAKEKeywordExtractor, SynonymExtractor
from app.services.system.components.generator.multi_query import MultiQueryAdjuster
from app.services.system.components.generator.query_adjust import (
    AbstractQueryAdjuster, QueryAdjusterAzureOpenAI, OllamaQueryAdjuster,
)
from app.services.system.components.post_processor import AbstractPostProcessor
from app.services.system.components.post_processor.chunk_filter import (
    ChunkFilterProcessor, TopNChunkFilter, DeduplicateChunkFilter, UsedInAnswerChunkFilter,
)
from app.services.system.components.post_processor.chunk_order import (
    ChunkOrderProcessor, ConcatenateChunkOrder, CrossEncoderChunkOrder, EmbeddingChunkOrder, LLMChunkOrder, PropertyForwardChunkOrder,
    WeightedSumChunkOrder,
)
from app.services.system.components.post_processor.context_retriever import ContextRetriever
from app.services.system.components.post_processor.hierarchy_retriever import HierarchyRetriever
from app.services.system.components.retriever import AbstractRetriever, VectorRetriever, MultiQueriesVectorRetriever
from app.services.system.components.structure import StartComponent, EndComponent, ListComponent, CodeExecutorComponent
from app.services.system.components.structure.decision import AbstractDecisionComponent, IfElseDecision, CaseDecision

AbstractGenerator.variants = {
    "azure_open_ai": AzureOpenAIGenerator,
    "ollama": OllamaGenerator,
}

AbstractRetriever.variants = {
    "vector_retriever": VectorRetriever,
    "multi_queries_vector_retriever": MultiQueriesVectorRetriever,
}

AbstractDecisionComponent.variants = {
    "if_else": IfElseDecision,
    "case": CaseDecision,
}

AbstractHyDEGenerator.variants = {
    "azure_open_ai": HyDEAzureOpenAIGenerator,
    "ollama": HyDEOllamaGenerator,
}

AbstractQueryAdjuster.variants = {
    "azure_open_ai": QueryAdjusterAzureOpenAI,
    "ollama": OllamaQueryAdjuster,
}

ChunkOrderProcessor.variants = {
    "concatenate": ConcatenateChunkOrder,
    "cross_encoding": CrossEncoderChunkOrder,
    "embedding": EmbeddingChunkOrder,
    "llm": LLMChunkOrder,
    "property_forward": PropertyForwardChunkOrder,
    "weighted_sum": WeightedSumChunkOrder,
}

ChunkFilterProcessor.variants = {
    "top_n": TopNChunkFilter,
    "deduplicate": DeduplicateChunkFilter,
    "used_in_answer": UsedInAnswerChunkFilter,
}

AbstractPostProcessor.variants = {
    "chunk_order": ChunkOrderProcessor,
    "chunk_filter": ChunkFilterProcessor,
    "add_context": ContextRetriever,
    "hierarchy_retrieval": HierarchyRetriever,
}

SplitComponent.variants = {
    "azure_open_ai": DecomposeSplitAzureOpenAIGenerator,
    "ollama": DecomposeSplitOllamaGenerator,
}

MergeComponent.variants = {
    "azure_open_ai": DecomposeMergeAzureOpenAIGenerator,
    "ollama": DecomposeMergeOllamaGenerator,
}

AbstractDecomposeComponent.variants = {
    "split": SplitComponent,
    "merge": MergeComponent,
}

AbstractJudge.variants = {
    "ragas": RAGAsJudge,
    "in_scope": QuestionInScopeJudge,
}

AbstractKeywordExtractor.variants = {
    "llm_extractor": LLMKeywordExtractor,
    "yake_extractor": YAKEKeywordExtractor,
}

AbstractComponent.variants = {
    "start": StartComponent,
    "end": EndComponent,
    "list": ListComponent,
    "decision": AbstractDecisionComponent,
    "judge": AbstractJudge,
    "generator": AbstractGenerator,
    "retriever": AbstractRetriever,
    "hyde_generator": AbstractHyDEGenerator,
    "query_adjuster": AbstractQueryAdjuster,
    "multi_query": MultiQueryAdjuster,
    "keyword_extractor": AbstractKeywordExtractor,
    "decompose": AbstractDecomposeComponent,
    "code_executor": CodeExecutorComponent,
    "post_processor": AbstractPostProcessor,
    # adaptive pattern
    "action_tracker": ActionTrackerComponent,
    "adapt_decision": AdaptDecisionComponent,
    "filter_action_path": FilterActionComponent,
    "retrieve_action_path": RetrieveActionComponent,
}
