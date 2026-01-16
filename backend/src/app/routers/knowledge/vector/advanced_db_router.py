import time
from typing import List

from fastapi import APIRouter, status, Depends, HTTPException

from app.models.knowledge.vector.advanced_db_models import RerankRequest, FilterTopNThresholdRequest, DeduplicateRequest, AutomergeRequest
from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchResult, WeaviateSearchChunkResult
from app.services.knowledge.vector import AdvancedDBService, HierarchicalIndexVectorDBService
from app.utils.logger import setup_logger
from app.utils.service_creators import get_advanced_db_service, get_hierarchical_vector_service

logger = setup_logger(name=__name__)
advanced_database_router = APIRouter()


@advanced_database_router.get("/rerank", status_code=status.HTTP_200_OK, response_model=List[str])
def list_reranker_options(
        service: AdvancedDBService = Depends(get_advanced_db_service),
):
    return service.available_rerankings()


@advanced_database_router.post("/rerank", status_code=status.HTTP_200_OK, response_model=WeaviateSearchResult)
def rerank_chunks(
        reranking_option: str,
        body: RerankRequest,
        service: AdvancedDBService = Depends(get_advanced_db_service),
):
    try:
        start = time.time()
        reranked_results = service.rerank(
            reranking_option=reranking_option,
            query=body.query,
            retrieved_chunks=body.original_search_result.results,
            **{k: v for k, v in body.model_dump().items() if k not in {"query", "reranking_option", "original_search_result"}},
        )
        end = time.time()
        return WeaviateSearchResult(
            results=reranked_results,
            duration=end - start,
        )
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@advanced_database_router.post("/deduplicate", status_code=status.HTTP_200_OK, response_model=WeaviateSearchResult)
def deduplicate_chunks(
        rank_method: str,
        body: DeduplicateRequest,
        service: AdvancedDBService = Depends(get_advanced_db_service),
):
    """
    Greedy duplicate filter driven by rerankers.
    rank_method is passed as a query parameter for symmetry with /rerank.
    """
    try:
        start = time.time()
        filtered_results: List[WeaviateSearchChunkResult] = service.filter_duplicates(
            retrieved_chunks=body.original_search_result.results,
            keep_all_guidelines=body.keep_all_guidelines,
            compared_property=body.compared_property,
            rank_method=rank_method,  # override with query param, like your /rerank endpoint
            cutoff_similarity=body.cutoff_similarity,
            **{
                k: v
                for k, v in body.model_dump().items()
                if k
                   not in {
                       "original_search_result",
                       "keep_all_guidelines",
                       "compared_property",
                       "rank_method",
                       "cutoff_similarity",
                   }
            },
        )
        end = time.time()
        return WeaviateSearchResult(results=filtered_results, duration=end - start)
    except ValueError as e:
        # e.g., unsupported rank_method or invalid args
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@advanced_database_router.post("/filter/topn_threshold", status_code=status.HTTP_200_OK, response_model=WeaviateSearchResult)
def filter_topn_threshold(
        body: FilterTopNThresholdRequest,
        service: AdvancedDBService = Depends(get_advanced_db_service),
):
    """
    Prunes by rerank score using top_n and/or threshold.
    """
    try:
        start = time.time()
        filtered_results: List[WeaviateSearchChunkResult] = service.filter_top_n_and_threshold(
            retrieved_chunks=body.original_search_result.results,
            top_n=body.top_n,
            threshold=body.threshold,
        )
        end = time.time()
        return WeaviateSearchResult(results=filtered_results, duration=end - start)
    except ValueError as e:
        # e.g., both top_n and threshold are None
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@advanced_database_router.post("/hierarchy/setup")
def setup_hierarchical_index_for_vector_db(
        weaviate_collection_name: str,
        force_update: bool = False,
        hier_service: HierarchicalIndexVectorDBService = Depends(get_hierarchical_vector_service),
):
    try:
        hier_service.build_automerge_retrieval_source(weaviate_collection_name, force_update=force_update)
        # return hier_service.print_hierarchy_graph(weaviate_collection_name)
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@advanced_database_router.post("/hierarchy/{weaviate_collection_name}/retrieve")
def retrieve_automerge(
        weaviate_collection_name: str,
        request: AutomergeRequest,
        hier_service: HierarchicalIndexVectorDBService = Depends(get_hierarchical_vector_service),
):
    try:
        return hier_service.retrieve_automerge(
            weaviate_collection_name, retrieval_start=request.original_search_result, simple_ratio_threshold=request.simple_ratio_threshold,
        )
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
