import os
from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.system.components.post_processor.chunk_order.abstract_chunk_order import ChunkOrderProcessor
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class LLMChunkOrder(ChunkOrderProcessor, variant_name="llm"):
    default_parameters: Dict[str, Any] = {
        **ChunkOrderProcessor.default_parameters,
        "compared_property": "text",
        "model": "gpt-4.1",
        "api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
        "api_base": os.getenv("AZURE_OPENAI_API_BASE", ""),
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.reranking_option = "llm"
        
        self.model = self.parameters.get("model") or self.default_parameters["model"]
        self.compared_property = self.parameters.get("compared_property") or self.default_parameters["compared_property"]
        self.api_key = self.parameters.get("api_key") or self.default_parameters["api_key"]
        self.api_base = self.parameters.get("api_base") or self.default_parameters["api_base"]
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "model": {
                    "type": "str",
                    "description": "LLM model used to create rerank scores; Options: [gpt-4.1, gpt-3.5, llama3-8b]",
                    "default": "gpt-4.1",
                },
                "compared_property": {
                    "type": "string",
                    "description": "Property of retrieved chunk which to compare to query",
                    "default": "text",
                },
                "api_key": {
                    "type": "string",
                    "description": "Azure OpenAI API key (only relevant for GPT models)",
                },
                "api_base": {
                    "type": "string",
                    "description": "API base URL to call model (default: used from environment variables)",
                },
            },
        )
        return base_params
    
    def process(self, query: str, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        return self.advanced_vector_service.rerank(
            reranking_option=self.reranking_option,
            query=query,
            retrieved_chunks=retrievals,
            model=self.model,
            compared_property=self.compared_property,
            api_key=self.api_key,
            api_base=self.api_base,
        )
