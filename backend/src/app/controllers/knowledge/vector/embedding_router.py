from fastapi import APIRouter, Depends, HTTPException, status

from app.constants.auth_config import ROLE_ADMIN
from app.controllers.dependencies.auth_dependencies import require_roles
from app.exceptions.knowledge.vector import VectorizerNotAvailableError, VectorizerNotFoundError
from app.models.knowledge.vector import EmbeddingRequest, EmbeddingResponse, VectorizerListResponse
from app.services.knowledge.vector import EmbeddingService
from app.services.service_registry import get_embedding_service
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

embedding_router = APIRouter()


@embedding_router.get(
    "/providers",
    response_model=VectorizerListResponse,
    summary="List configured embedding providers (admin only)",
    description="Shows which vectorizers are registered and whether they are currently usable in this environment.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def list_embedding_providers(service: EmbeddingService = Depends(get_embedding_service)) -> VectorizerListResponse:
    return VectorizerListResponse(vectorizers=service.list_vectorizers())


@embedding_router.post(
    "/embed",
    response_model=EmbeddingResponse,
    status_code=status.HTTP_200_OK,
    summary="Embed one or more texts (admin only)",
    description=(
        "Embeds the provided texts with the selected provider. "
        "This is useful for quick diagnostics, retrieval experiments, and vector-db ingestion."
    ),
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def create_embeddings(
        request: EmbeddingRequest,
        service: EmbeddingService = Depends(get_embedding_service),
) -> EmbeddingResponse:
    try:
        embeddings = service.embed_texts(
            request.provider,
            request.texts,
            provider_settings=request.provider_settings,
            purpose=request.purpose,
            normalize=request.normalize,
        )
        dimensions = len(embeddings[0]) if embeddings else 0
        return EmbeddingResponse(
            provider=request.provider,
            purpose=request.purpose,
            normalize=request.normalize,
            dimensions=dimensions,
            embeddings=embeddings,
        )
    except VectorizerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except VectorizerNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Embedding request failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
