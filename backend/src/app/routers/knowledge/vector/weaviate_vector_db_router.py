from typing import List, Optional

from fastapi import APIRouter, status, Depends, HTTPException, Query

from app.models.knowledge.vector.weaviate_related_models import (
    WeaviateCollection, WeaviateSearchResult, WeaviateSingleSearchProperties, WeaviateMultiSearchProperties,
)
from app.services.knowledge.guidelines import GuidelineService
from app.services.knowledge.guidelines.references import GuidelineReferenceService
from app.services.knowledge.vector import WeaviateVectorDBService
from app.utils.logger import setup_logger
from app.utils.service_creators import get_guideline_service, get_vector_db_service, get_guideline_reference_service

logger = setup_logger(name=__name__)
vector_database_router = APIRouter()


@vector_database_router.get("/vectorizers", status_code=status.HTTP_200_OK, response_model=List[str])
def list_vectorizers(
        service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    """
    List all available vectorizers (used upon insertion of entry in vector database -> will apply one of the vectorizers)
    """
    return service.get_available_vectorizers()


@vector_database_router.get("/distance_metrics", status_code=status.HTTP_200_OK, response_model=List[str])
def list_distance_metrics(
        service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    return service.get_available_distance_metrics()


@vector_database_router.post("/collection", status_code=status.HTTP_200_OK)
def create_collection(
        collection: WeaviateCollection,
        service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        logger.debug("Create collection")
        service.create_collection(collection)
        logger.info("List created collection")
        return service.get_collection(collection.collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.get("/collection", status_code=status.HTTP_200_OK, response_model=List[WeaviateCollection])
def list_collections(
        service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        return service.list_collections()
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.get(
    "/collection/{collection_name}", status_code=status.HTTP_200_OK, response_model=WeaviateCollection,
)
def get_collection(
        collection_name: str,
        service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        return service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.delete("/collection/{collection_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
        collection_name: str,
        service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        service.delete_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.post("/collection/{collection_name}/insert", status_code=status.HTTP_200_OK)
def insert_chunk(
        collection_name: str,
        chunk: dict,
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        gl_reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
):
    try:
        vector_service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        guideline_service.get_guideline_by_id(chunk["guideline_id"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gl_ref = gl_reference_service.get_reference_by_id(chunk["reference_id"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    if str(gl_ref.guideline_id) != (chunk["guideline_id"]):
        logger.warning(
            f"Missmatch in guideline -> "
            f"Guideline ID in chunk: '{chunk['guideline_id']}'; Guideline ID in reference: '{gl_ref.guideline_id}'",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reference does not belong to the same guideline",
        )
    
    try:
        return vector_service.insert_chunk(collection_name, chunk)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.post("/collection/{collection_name}/insert_bulk", status_code=status.HTTP_200_OK)
def insert_chunks(
        collection_name: str,
        chunks: List[dict],
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        gl_reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
):
    try:
        vector_service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    for chunk in chunks:
        try:
            guideline_service.get_guideline_by_id(chunk["guideline_id"])
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except Exception as e:
            logger.error(str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        
        try:
            gl_ref = gl_reference_service.get_reference_by_id(chunk["reference_id"])
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except Exception as e:
            logger.error(str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        
        if str(gl_ref.guideline_id) != (chunk["guideline_id"]):
            logger.warning(
                f"Missmatch in guideline for chunk {chunk} -> "
                f"Guideline ID in chunk: '{chunk['guideline_id']}'; Guideline ID in reference: '{gl_ref.guideline_id}'",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reference does not belong to the same guideline",
            )
    
    try:
        inserted = []
        for chunk in chunks:
            inserted.append(vector_service.insert_chunk(collection_name, chunk))
        return inserted
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.delete("/collection/{collection_name}/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_chunk(
        collection_name: str,
        chunk: dict,
        delete_related_ref: bool = Query(
            default=False, description="Whether to delete the reference linked to the chunk entry as well.",
        ),
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
        gl_reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
):
    try:
        vector_service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    if delete_related_ref:
        try:
            gl_reference_service.delete_reference_by_id(chunk["reference_id"])
        except ValueError as e:
            logger.warning(f"Error deleting reference: {str(e)} (does not exist?)", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reference with ID {chunk['reference_id']} not found",
            )
        except Exception as e:
            logger.error(f"Error deleting reference with ID {chunk['reference_id']}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting reference: {str(e)}",
            )
    
    try:
        vector_service.remove_chunk(collection_name, chunk)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.put("/collection/{collection_name}/update", status_code=status.HTTP_200_OK)
def update_chunk(
        collection_name: str,
        original_chunk: dict,
        update_chunk: dict,
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        gl_reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
):
    try:
        vector_service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    try:
        guideline_service.get_guideline_by_id(update_chunk["guideline_id"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        gl_ref = gl_reference_service.get_reference_by_id(update_chunk["reference_id"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    if str(gl_ref.guideline_id) != (update_chunk["guideline_id"]):
        logger.warning(
            f"Missmatch in guideline -> "
            f"Guideline ID in chunk: '{update_chunk['guideline_id']}'; Guideline ID in reference: '{gl_ref.guideline_id}'",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reference does not belong to the same guideline",
        )
    
    try:
        return vector_service.update_chunk(
            collection_name, original_chunk=original_chunk, new_chunk=update_chunk,
        )
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.post("/collection/{collection_name}/single_search", status_code=status.HTTP_200_OK, response_model=WeaviateSearchResult)
def single_query_search_for_chunks(
        collection_name: str,
        search_properties: WeaviateSingleSearchProperties,
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        vector_service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return vector_service.single_query_search(
            collection_name=collection_name, query=search_properties.query, top_k=search_properties.top_k,
            distance_threshold=search_properties.distance_threshold, score_threshold=search_properties.score_threshold,
            overwrite_vectorizer_manual_weights=search_properties.overwrite_vectorizer_manual_weights,
            bm25_search_properties=search_properties.bm25_search_properties, alpha=search_properties.alpha,
        )
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.post("/collection/{collection_name}/multi_search", status_code=status.HTTP_200_OK, response_model=WeaviateSearchResult)
def multi_queries_search_for_chunks(
        collection_name: str,
        search_properties: WeaviateMultiSearchProperties,
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        vector_service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return vector_service.multi_query_search(
            collection_name=collection_name, queries=search_properties.queries, top_k=search_properties.top_k,
            distance_threshold=search_properties.distance_threshold, score_threshold=search_properties.score_threshold,
            bm25_query=search_properties.bm25_query, bm25_search_properties=search_properties.bm25_search_properties, alpha=search_properties.alpha,
        )
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.get("/collection/{collection_name}/count_chunks", status_code=status.HTTP_200_OK)
def count_chunks_in_collection(
        collection_name: str,
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        return vector_service.count_chunks(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.get("/collection/{collection_name}/get_average_property_len", status_code=status.HTTP_200_OK)
def calculate_average_len_chunk_property(
        collection_name: str,
        property_name: str,
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        return vector_service.average_len_chunk_property(collection_name, property_name=property_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.put(
    "/collection/{collection_name}/list_chunks", status_code=status.HTTP_200_OK, response_model=List[dict],
)
def list_chunks_in_collection(
        collection_name: str,
        guideline_id: Optional[str] = Query(
            default=None,
            description="If provided, only chunks belonging to the guideline with the given ID will be returned",
        ),
        reference_id: Optional[str] = Query(
            default=None,
            description="If provided, only chunks belonging to the reference with the given ID will be returned",
        ),
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
        guideline_service: GuidelineService = Depends(get_guideline_service),
        gl_reference_service: GuidelineReferenceService = Depends(get_guideline_reference_service),
):
    try:
        vector_service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    if guideline_id is not None:
        try:
            guideline_service.get_guideline_by_id(guideline_id)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except Exception as e:
            logger.error(str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    if reference_id is not None:
        try:
            gl_reference_service.get_reference_by_id(reference_id)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except Exception as e:
            logger.error(str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return vector_service.list_chunks_in_collection(collection_name, guideline_id=guideline_id, reference_id=reference_id)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@vector_database_router.get("/collection/{collection_name}/get_chunk", response_model=dict, status_code=status.HTTP_200_OK)
def get_chunk_by_chunk_index(
        collection_name: str,
        chunk_index: int,
        vector_service: WeaviateVectorDBService = Depends(get_vector_db_service),
):
    try:
        vector_service.get_collection(collection_name)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    try:
        return vector_service.find_by_chunk_index(collection_name, chunk_index)
    except ValueError as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
