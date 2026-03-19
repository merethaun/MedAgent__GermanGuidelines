from fastapi import APIRouter, Depends, HTTPException, status

from app.constants.auth_config import ROLE_ADMIN, ROLE_USER
from app.constants.neo4j_constants import NEO4J_URI
from app.controllers.dependencies.auth_dependencies import require_roles
from app.exceptions.knowledge.graph import GraphNotFoundError
from app.models.knowledge.graph import GraphRetrieveRequest, GraphRetrieveResponse, GraphStatusResponse, GraphSyncRequest, GraphSyncResponse
from app.services.knowledge.graph import Neo4jGraphService
from app.services.service_registry import get_graph_service
from app.utils.logging import setup_logger

logger = setup_logger(__name__)

graph_router = APIRouter()


@graph_router.get(
    "/health",
    response_model=GraphStatusResponse,
    summary="Check Neo4j availability (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def health(service: Neo4jGraphService = Depends(get_graph_service)) -> GraphStatusResponse:
    try:
        return GraphStatusResponse(available=service.ping(), uri=NEO4J_URI)
    except Exception as exc:
        logger.error("Neo4j health check failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail=str(exc))


@graph_router.post(
    "/retrieve",
    response_model=GraphRetrieveResponse,
    summary="Expand seed references via the Neo4j graph (admin + study_user)",
    description="Takes a seed set of guideline references and expands it through the Neo4j graph.",
    dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))],
)
def retrieve(
        request: GraphRetrieveRequest,
        service: Neo4jGraphService = Depends(get_graph_service),
) -> GraphRetrieveResponse:
    try:
        references, added_references, hits, latency = service.expand_from_references(
            graph_name=request.settings.graph_name,
            seed_references=request.references,
            result_limit=request.settings.limit,
            include_seed_references=request.settings.include_seed_references,
            neighbor_depth=request.settings.neighbor_depth,
            include_section_references=request.settings.include_section_references,
            section_max_children=request.settings.section_max_children,
            include_keyword_matches=request.settings.include_keyword_matches,
            keyword_overlap_min=request.settings.keyword_overlap_min,
            keyword_overlap_ratio_min=request.settings.keyword_overlap_ratio_min,
            include_similarity_matches=request.settings.include_similarity_matches,
            similarity_threshold=request.settings.similarity_threshold,
        )
        return GraphRetrieveResponse(references=references, added_references=added_references, graph_hits=hits, latency=latency)
    except GraphNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Neo4j retrieval failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@graph_router.post(
    "/sync-reference-group",
    response_model=GraphSyncResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sync one reference group into Neo4j (admin only)",
    description="Builds a guideline graph in Neo4j from stored guideline references. Interaction happens with the database through this backend API.",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def sync_reference_group(
        request: GraphSyncRequest,
        service: Neo4jGraphService = Depends(get_graph_service),
) -> GraphSyncResponse:
    try:
        return service.sync_reference_group(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Neo4j sync failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@graph_router.delete(
    "/graphs/{graph_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one Neo4j graph (admin only)",
    dependencies=[Depends(require_roles(ROLE_ADMIN))],
)
def delete_graph(
        graph_name: str,
        service: Neo4jGraphService = Depends(get_graph_service),
) -> None:
    try:
        service.delete_graph(graph_name)
        return None
    except Exception as exc:
        logger.error("Neo4j delete failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
