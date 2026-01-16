from typing import Dict, Any, List

from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.knowledge.vector import WeaviateVectorDBService
from app.services.system.components.post_processor.abstract_post_processor import AbstractPostProcessor
from app.utils.logger import setup_logger
from app.utils.service_creators import get_vector_db_service

logger = setup_logger(__name__)


def add_context(retrievals, assert_same_property, context_size, weaviate_vector_service, weaviate_collection):
    final_retrieval = []
    
    def hash_dict(d):
        return hash(tuple(sorted(d.items())))
    
    for retrieval in retrievals:
        score = retrieval.score
        
        base_chunk = retrieval.retrieved_chunk
        chunk_index = base_chunk.get("chunk_index")
        guideline_id = base_chunk.get("guideline_id")
        if chunk_index is None or guideline_id is None:
            raise ValueError(f"[ContextRetriever] Missing 'chunk_index' or 'guideline_id' in retrieval: {retrieval}")
        
        relevant_base_properties = {}
        for prop in assert_same_property:
            relevant_base_properties[prop] = base_chunk.get(prop)
        context_chunks = [base_chunk]
        
        for direction in (-1, 1):  # -1 = front, +1 = back
            for i in range(1, context_size + 1):
                idx = chunk_index + direction * i
                try:
                    chunk = weaviate_vector_service.find_by_chunk_index(weaviate_collection, idx)
                    if chunk.get("guideline_id") != guideline_id:
                        raise ValueError(f"[ContextRetriever] Guideline mismatch at index {idx}")
                    
                    for prop, value in relevant_base_properties.items():
                        if chunk.get(prop) != value:
                            logger.info(f"[ContextRetriever] Property mismatch at index {idx} -> not include")
                    
                    if direction == -1:
                        context_chunks.insert(0, chunk)
                    else:
                        context_chunks.append(chunk)
                
                except ValueError as e:
                    logger.warning(f"[ContextRetriever] Context boundary reached at index {idx}: {e}")
                    break
        
        for chunk in context_chunks:
            final_retrieval.append(
                (
                    hash_dict(chunk),
                    WeaviateSearchChunkResult(
                        retrieved_chunk=chunk,
                        score=score,
                        context_for=chunk["reference_id"],
                    ),
                ),
            )
    
    used_hash_dicts = []
    final_filtered_retrieval = []
    for hashed_dict, retrieval in final_retrieval:
        if hashed_dict not in used_hash_dicts:
            used_hash_dicts.append(hashed_dict)
            final_filtered_retrieval.append(retrieval)
    
    return final_filtered_retrieval


class ContextRetriever(AbstractPostProcessor, variant_name="add_context"):
    default_parameters: Dict[str, Any] = {
        **AbstractPostProcessor.default_parameters,
        "context_size": 1,
    }
    
    def __init__(self, component_id: str, name: str, parameters: Dict[str, Any], variant: str = None):
        super().__init__(component_id, name, parameters, variant)
        self.weaviate_vector_service: WeaviateVectorDBService = get_vector_db_service()
        
        self.context_size = self.parameters.get("context_size") or self.default_parameters["context_size"]
        self.assert_same_property = self.parameters.get("assert_same_property", [])
        self.weaviate_collection = self.parameters.get("weaviate_collection")
    
    @classmethod
    def get_init_parameters(cls) -> Dict[str, Dict[str, Any]]:
        base_params = super().get_init_parameters()
        base_params.update(
            {
                "weaviate_collection": {
                    "type": "string",
                    "description": "Weaviate collection to use for the retrieval (will send query, top_k)",
                },
                "context_size": {
                    "type": "int", "description": "The 'padding' size around the original retrieval results where to look for context",
                },
                "assert_same_property": {
                    "type": "list",
                    "description": "A list of properties that needs to match with the chunk to add context to.",
                    "default": [],
                },
            },
        )
        return base_params
    
    def process(self, _, retrievals: List[WeaviateSearchChunkResult], data: Dict[str, Any]) -> List[WeaviateSearchChunkResult]:
        final_retrieval = add_context(
            retrievals, self.assert_same_property, self.context_size, self.weaviate_vector_service, self.weaviate_collection,
        )
        
        logger.debug(
            f"[ContextRetriever] Retrieved {len(final_retrieval)} unique chunks (added {len(final_retrieval) - len(retrievals)} context chunks)",
        )
        return final_retrieval
