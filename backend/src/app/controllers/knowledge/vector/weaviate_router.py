from fastapi import APIRouter, Depends, HTTPException, status

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import require_roles
from app.exceptions.knowledge.vector import VectorCollectionNotFoundError, VectorizerNotAvailableError, VectorizerNotFoundError
from app.models.knowledge.vector import (
    CreateWeaviateCollectionRequest,
    DeleteGuidelineResponse,
    IngestGuidelineRequest,
    IngestReferenceGroupRequest,
    IngestReferenceGroupResponse,
    WeaviateCapabilitiesResponse,
    WeaviateCollectionResponse,
    WeaviateObjectResponse,
    WeaviateSearchRequest,
    WeaviateSearchResponse,
    WeaviateUpsertObjectRequest,
)
from app.services.knowledge.vector import EmbeddingService, WeaviateVectorStoreService
from app.services.service_registry import get_embedding_service, get_weaviate_vector_store_service
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

weaviate_router = APIRouter()


@weaviate_router.get(
    "/capabilities",
    response_model=WeaviateCapabilitiesResponse,
    summary="Inspect Weaviate/vectorizer capabilities (admin only)",
    description="Returns supported distance metrics together with registered embedding providers.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def get_weaviate_capabilities(
        weaviate_service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
        embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> WeaviateCapabilitiesResponse:
    return WeaviateCapabilitiesResponse(
        distance_metrics=weaviate_service.list_distance_metrics(),
        vectorizers=embedding_service.list_vectorizers(),
    )


@weaviate_router.get(
    "/collections",
    response_model=list[WeaviateCollectionResponse],
    summary="List vector collections (admin only)",
    description="Lists the vector collections known to the backend together with their embedding configuration.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def list_vector_collections(
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> list[WeaviateCollectionResponse]:
    return service.list_collections()


@weaviate_router.post(
    "/collections",
    response_model=WeaviateCollectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a vector collection (admin only)",
    description="Creates a manual-vector Weaviate collection and stores its embedding schema in MongoDB.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_vector_collection(
        request: CreateWeaviateCollectionRequest,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> WeaviateCollectionResponse:
    try:
        return service.create_collection(request)
    except (VectorizerNotFoundError, VectorizerNotAvailableError, ValueError) as exc:
        status_code = 503 if isinstance(exc, VectorizerNotAvailableError) else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    except Exception as exc:
        logger.error("Create Weaviate collection failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@weaviate_router.get(
    "/collections/{collection_name}",
    response_model=WeaviateCollectionResponse,
    summary="Get one vector collection (admin only)",
    description="Returns the stored embedding schema for a single Weaviate collection.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def get_vector_collection(
        collection_name: str,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> WeaviateCollectionResponse:
    try:
        return service.get_collection(collection_name)
    except VectorCollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@weaviate_router.delete(
    "/collections/{collection_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a vector collection (admin only)",
    description="Deletes the Weaviate collection and its stored backend metadata.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_vector_collection(
        collection_name: str,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> None:
    try:
        service.delete_collection(collection_name)
        return None
    except VectorCollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Delete Weaviate collection failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@weaviate_router.post(
    "/collections/{collection_name}/objects",
    response_model=WeaviateObjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Insert one object into a vector collection (admin only)",
    description="Embeds the configured source properties and writes the object plus named vectors into Weaviate.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def insert_vector_object(
        collection_name: str,
        request: WeaviateUpsertObjectRequest,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> WeaviateObjectResponse:
    try:
        return service.insert_object(
            collection_name,
            request.properties,
            provider_settings=request.provider_settings,
        )
    except VectorCollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (VectorizerNotFoundError, VectorizerNotAvailableError) as exc:
        status_code = 503 if isinstance(exc, VectorizerNotAvailableError) else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Insert Weaviate object failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@weaviate_router.delete(
    "/collections/{collection_name}/objects/{object_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one object from a vector collection (admin only)",
    description="Deletes a Weaviate object by UUID.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_vector_object(
        collection_name: str,
        object_id: str,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> None:
    try:
        service.delete_object(collection_name, object_id)
        return None
    except VectorCollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Delete Weaviate object failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@weaviate_router.post(
    "/collections/{collection_name}/search",
    response_model=WeaviateSearchResponse,
    summary="Search a vector collection (admin only)",
    description=(
            "Runs vector or hybrid search against one named vector. "
            "Hybrid mode combines BM25 over keyword_properties with the selected query embedding."
    ),
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def search_vector_collection(
        collection_name: str,
        request: WeaviateSearchRequest,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> WeaviateSearchResponse:
    try:
        return service.search(collection_name, request)
    except VectorCollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (VectorizerNotFoundError, VectorizerNotAvailableError) as exc:
        status_code = 503 if isinstance(exc, VectorizerNotAvailableError) else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Weaviate search failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@weaviate_router.post(
    "/collections/{collection_name}/ingest-reference-group",
    response_model=IngestReferenceGroupResponse,
    summary="Ingest the linked reference group into a vector collection (admin only)",
    description=(
            "Reads all references from the collection's linked reference group, maps them into collection properties "
            "using the stored ingestion mapping, computes named vectors, and inserts the resulting objects into Weaviate. "
            "If guideline_id is supplied in the request body, only that guideline is replaced."
    ),
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def ingest_reference_group(
        collection_name: str,
        request: IngestReferenceGroupRequest,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> IngestReferenceGroupResponse:
    try:
        return service.ingest_reference_group(
            collection_name,
            guideline_id=request.guideline_id,
            provider_settings=request.provider_settings,
            continue_on_error=request.continue_on_error,
        )
    except VectorCollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (VectorizerNotFoundError, VectorizerNotAvailableError) as exc:
        status_code = 503 if isinstance(exc, VectorizerNotAvailableError) else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Reference-group ingestion failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@weaviate_router.put(
    "/collections/{collection_name}/guidelines/{guideline_id}",
    response_model=IngestReferenceGroupResponse,
    summary="Replace one guideline inside a vector collection (admin only)",
    description="Deletes the collection objects for one guideline and recreates them from the linked reference group. Chunk indices restart at 0 for that guideline.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def upsert_guideline_in_collection(
        collection_name: str,
        guideline_id: str,
        request: IngestGuidelineRequest,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> IngestReferenceGroupResponse:
    try:
        return service.upsert_guideline(collection_name, guideline_id, request)
    except VectorCollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (VectorizerNotFoundError, VectorizerNotAvailableError) as exc:
        status_code = 503 if isinstance(exc, VectorizerNotAvailableError) else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Guideline upsert failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@weaviate_router.delete(
    "/collections/{collection_name}/guidelines/{guideline_id}",
    response_model=DeleteGuidelineResponse,
    summary="Delete one guideline from a vector collection (admin only)",
    description="Deletes all vector objects in the collection that belong to the given guideline_id.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_guideline_from_collection(
        collection_name: str,
        guideline_id: str,
        service: WeaviateVectorStoreService = Depends(get_weaviate_vector_store_service),
) -> DeleteGuidelineResponse:
    try:
        return service.delete_guideline_objects(collection_name, guideline_id)
    except VectorCollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Guideline delete failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
