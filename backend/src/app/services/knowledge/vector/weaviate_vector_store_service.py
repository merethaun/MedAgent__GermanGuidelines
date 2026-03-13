import os
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse
from types import SimpleNamespace

from app.exceptions.knowledge.vector import VectorCollectionNotFoundError
from app.models.knowledge.guideline import ReferenceType
from app.models.knowledge.vector import (
    CreateWeaviateCollectionRequest,
    DeleteGuidelineResponse,
    EmbeddingProviderSettings,
    EmbeddingPurpose,
    IngestGuidelineRequest,
    IngestReferenceGroupResponse,
    MetadataContentMode,
    VectorCollectionMappedField,
    WeaviateCollectionResponse,
    WeaviateObjectResponse,
    WeaviateSearchHit,
    WeaviateSearchMode,
    WeaviateSearchRequest,
    WeaviateSearchResponse,
)
from app.services.knowledge.vector.embedding_service import EmbeddingService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


SUPPORTED_DISTANCE_METRICS = ["cosine", "dot", "l2-squared", "manhattan", "hamming"]
WEAVIATE_DATA_TYPE_MEMBER_MAP = {
    "text": "TEXT",
    "text[]": "TEXT_ARRAY",
    "int": "INT",
    "int[]": "INT_ARRAY",
    "number": "NUMBER",
    "number[]": "NUMBER_ARRAY",
    "boolean": "BOOL",
    "boolean[]": "BOOL_ARRAY",
    "date": "DATE",
    "date[]": "DATE_ARRAY",
    "uuid": "UUID",
    "uuid[]": "UUID_ARRAY",
    "geocoordinates": "GEO_COORDINATES",
    "blob": "BLOB",
    "phonenumber": "PHONE_NUMBER",
    "object": "OBJECT",
    "object[]": "OBJECT_ARRAY",
}


class WeaviateVectorStoreService:
    """
    Small Weaviate integration layer for manual-vector collections.

    Collection schemas are persisted in MongoDB so the backend knows which local
    embedding provider to use for each named vector during inserts and search.
    """

    WEAVIATE_DATA_TYPE_MEMBER_MAP = WEAVIATE_DATA_TYPE_MEMBER_MAP

    def __init__(
            self,
            metadata_collection,
            embedding_service: EmbeddingService,
            guideline_service,
            guideline_reference_service,
            client_factory: Optional[Callable[[], Any]] = None,
    ):
        self.metadata_collection = metadata_collection
        self.embedding_service = embedding_service
        self.guideline_service = guideline_service
        self.guideline_reference_service = guideline_reference_service
        self._client_factory = client_factory or self._build_client
        self._client = None

    def list_distance_metrics(self) -> List[str]:
        return list(SUPPORTED_DISTANCE_METRICS)

    def list_collections(self) -> List[WeaviateCollectionResponse]:
        documents = self.metadata_collection.find({}, {"_id": 0})
        return [WeaviateCollectionResponse(**document) for document in documents]

    def get_collection(self, collection_name: str) -> WeaviateCollectionResponse:
        document = self.metadata_collection.find_one({"name": collection_name}, {"_id": 0})
        if document is None:
            raise VectorCollectionNotFoundError(f"Unknown vector collection: {collection_name}")
        return WeaviateCollectionResponse(**document)

    def create_collection(self, request: CreateWeaviateCollectionRequest) -> WeaviateCollectionResponse:
        if not request.name[0].isupper():
            raise ValueError("Weaviate collection names must start with an uppercase letter.")

        if request.name in {collection.name for collection in self.list_collections()}:
            raise ValueError(f"Vector collection '{request.name}' already exists.")

        for named_vector in request.named_vectors:
            if named_vector.distance_metric not in SUPPORTED_DISTANCE_METRICS:
                raise ValueError(
                    f"Unsupported distance metric '{named_vector.distance_metric}'. "
                    f"Supported values: {', '.join(SUPPORTED_DISTANCE_METRICS)}",
                )
            self.embedding_service.get_vectorizer(named_vector.provider)

        client = self._get_client()
        self._create_weaviate_collection(client, request)
        self.metadata_collection.update_one(
            {"name": request.name},
            {"$set": request.model_dump()},
            upsert=True,
        )
        logger.info("Created Weaviate collection metadata for %s", request.name)
        return WeaviateCollectionResponse(**request.model_dump())

    def delete_collection(self, collection_name: str) -> None:
        collection = self.get_collection(collection_name)
        client = self._get_client()
        if client.collections.exists(collection.name):
            client.collections.delete(collection.name)
        self.metadata_collection.delete_one({"name": collection_name})
        logger.info("Deleted Weaviate collection %s", collection_name)

    def insert_object(
            self,
            collection_name: str,
            properties: Dict[str, Any],
            provider_settings: Optional[List[EmbeddingProviderSettings]] = None,
    ) -> WeaviateObjectResponse:
        collection = self.get_collection(collection_name)
        vectors = self._build_named_vectors(collection, properties, provider_settings=provider_settings or [])
        client_collection = self._get_client().collections.get(collection.name)
        object_uuid = client_collection.data.insert(properties=properties, vector=vectors)
        return WeaviateObjectResponse(uuid=str(object_uuid), properties=properties)

    def delete_object(self, collection_name: str, object_id: str) -> None:
        collection = self.get_collection(collection_name)
        self._get_client().collections.get(collection.name).data.delete_by_id(object_id)

    def ingest_reference_group(
            self,
            collection_name: str,
            *,
            guideline_id: Optional[str] = None,
            provider_settings: Optional[List[EmbeddingProviderSettings]] = None,
            continue_on_error: bool = False,
    ) -> IngestReferenceGroupResponse:
        if guideline_id is not None:
            return self.upsert_guideline(
                collection_name,
                guideline_id,
                IngestGuidelineRequest(provider_settings=provider_settings or []),
            )

        collection = self.get_collection(collection_name)
        references = self.guideline_reference_service.list_references(reference_group_id=collection.reference_group_id)
        references = sorted(references, key=self._reference_sort_key)

        guideline_cache: Dict[str, Any] = {}
        skipped_reference_ids: List[str] = []
        failed_reference_ids: List[str] = []
        inserted_object_count = 0
        chunk_index_by_guideline: Dict[str, int] = {}

        for reference in references:
            reference_id = str(reference.id)
            try:
                content = self._extract_reference_content(reference, collection.ingestion_mapping.metadata_content_mode)
                if not content:
                    if collection.ingestion_mapping.skip_references_without_content:
                        skipped_reference_ids.append(reference_id)
                        continue
                    raise ValueError(f"Reference {reference_id} has no content after mapping")

                properties = {
                    collection.ingestion_mapping.content_property: content,
                    "chunk_index": chunk_index_by_guideline.get(str(reference.guideline_id), 0),
                    "guideline_id": str(reference.guideline_id),
                    "reference_id": reference_id,
                }
                guideline = self._get_guideline_cached(str(reference.guideline_id), guideline_cache)
                for property_name, mapped_field in collection.ingestion_mapping.mapped_properties.items():
                    properties[property_name] = self._map_property_value(mapped_field, reference, guideline)

                self.insert_object(
                    collection_name,
                    properties,
                    provider_settings=provider_settings or [],
                )
                inserted_object_count += 1
                chunk_index_by_guideline[str(reference.guideline_id)] = properties["chunk_index"] + 1
            except Exception:
                failed_reference_ids.append(reference_id)
                if not continue_on_error:
                    raise

        return IngestReferenceGroupResponse(
            collection_name=collection.name,
            reference_group_id=collection.reference_group_id,
            inserted_object_count=inserted_object_count,
            skipped_reference_ids=skipped_reference_ids,
            failed_reference_ids=failed_reference_ids,
        )

    def upsert_guideline(
            self,
            collection_name: str,
            guideline_id: str,
            request: IngestGuidelineRequest,
    ) -> IngestReferenceGroupResponse:
        collection = self.get_collection(collection_name)
        references = self.guideline_reference_service.list_references(
            reference_group_id=collection.reference_group_id,
            guideline_id=guideline_id,
        )
        references = sorted(references, key=self._reference_sort_key)
        deleted_count = self.delete_guideline_objects(collection_name, guideline_id).deleted_object_count

        guideline_cache: Dict[str, Any] = {}
        skipped_reference_ids: List[str] = []
        failed_reference_ids: List[str] = []
        inserted_object_count = 0
        chunk_index = 0

        for reference in references:
            reference_id = str(reference.id)
            try:
                content = self._extract_reference_content(reference, collection.ingestion_mapping.metadata_content_mode)
                if not content:
                    if collection.ingestion_mapping.skip_references_without_content:
                        skipped_reference_ids.append(reference_id)
                        continue
                    raise ValueError(f"Reference {reference_id} has no content after mapping")

                properties = {
                    collection.ingestion_mapping.content_property: content,
                    "chunk_index": chunk_index,
                    "guideline_id": str(reference.guideline_id),
                    "reference_id": reference_id,
                }
                guideline = self._get_guideline_cached(str(reference.guideline_id), guideline_cache)
                for property_name, mapped_field in collection.ingestion_mapping.mapped_properties.items():
                    properties[property_name] = self._map_property_value(mapped_field, reference, guideline)

                self.insert_object(
                    collection_name,
                    properties,
                    provider_settings=request.provider_settings,
                )
                inserted_object_count += 1
                chunk_index += 1
            except Exception:
                failed_reference_ids.append(reference_id)
                raise

        logger.info(
            "Replaced guideline %s in collection %s (deleted=%d inserted=%d)",
            guideline_id,
            collection_name,
            deleted_count,
            inserted_object_count,
        )
        return IngestReferenceGroupResponse(
            collection_name=collection.name,
            reference_group_id=collection.reference_group_id,
            inserted_object_count=inserted_object_count,
            skipped_reference_ids=skipped_reference_ids,
            failed_reference_ids=failed_reference_ids,
        )

    def delete_guideline_objects(self, collection_name: str, guideline_id: str) -> DeleteGuidelineResponse:
        collection = self.get_collection(collection_name)
        client_collection = self._get_client().collections.get(collection.name)
        objects = self._fetch_objects_by_guideline(client_collection, guideline_id)
        for obj in objects:
            client_collection.data.delete_by_id(str(obj.uuid))
        return DeleteGuidelineResponse(
            collection_name=collection.name,
            guideline_id=guideline_id,
            deleted_object_count=len(objects),
        )

    def search(self, collection_name: str, request: WeaviateSearchRequest) -> WeaviateSearchResponse:
        collection = self.get_collection(collection_name)
        named_vector = next((entry for entry in collection.named_vectors if entry.name == request.vector_name), None)
        if named_vector is None:
            raise ValueError(f"Unknown named vector '{request.vector_name}' for collection '{collection_name}'.")

        query_vector = self.embedding_service.embed_texts(
            named_vector.provider,
            [request.query],
            provider_settings=self._get_provider_settings(request.provider_settings, named_vector.provider),
            purpose=EmbeddingPurpose.QUERY,
            normalize=False,
        )[0]
        client_collection = self._get_client().collections.get(collection.name)

        if request.mode == WeaviateSearchMode.HYBRID:
            result = client_collection.query.hybrid(
                query=request.query,
                vector=query_vector,
                target_vector=request.vector_name,
                query_properties=request.keyword_properties or None,
                alpha=request.alpha,
                limit=request.limit,
                return_metadata=self._metadata_query(score=True, distance=True),
            )
        else:
            result = client_collection.query.near_vector(
                near_vector=query_vector,
                target_vector=request.vector_name,
                limit=request.limit,
                return_metadata=self._metadata_query(score=True, distance=True),
            )

        hits = []
        for obj in result.objects:
            score = getattr(obj.metadata, "score", None)
            if request.minimum_score is not None and score is not None and score < request.minimum_score:
                continue
            hits.append(
                WeaviateSearchHit(
                    uuid=str(obj.uuid),
                    score=score,
                    distance=getattr(obj.metadata, "distance", None),
                    properties=obj.properties or {},
                ),
            )

        return WeaviateSearchResponse(
            collection_name=collection.name,
            vector_name=request.vector_name,
            mode=request.mode,
            hits=hits,
        )

    def _build_named_vectors(
            self,
            collection: WeaviateCollectionResponse,
            properties: Dict[str, Any],
            *,
            provider_settings: List[EmbeddingProviderSettings],
    ) -> Dict[str, List[float]]:
        vectors: Dict[str, List[float]] = {}
        for named_vector in collection.named_vectors:
            raw_value = properties.get(named_vector.source_property)
            if raw_value is None:
                continue
            text = str(raw_value).strip()
            if not text:
                continue
            vectors[named_vector.name] = self.embedding_service.embed_texts(
                named_vector.provider,
                [text],
                provider_settings=self._get_provider_settings(provider_settings, named_vector.provider),
                purpose=EmbeddingPurpose.DOCUMENT,
                normalize=False,
            )[0]
        if not vectors:
            raise ValueError("Object does not contain any non-empty named-vector source properties.")
        return vectors

    @staticmethod
    def _get_provider_settings(
            provider_settings: List[EmbeddingProviderSettings],
            provider: str,
    ) -> Optional[EmbeddingProviderSettings]:
        matches = [entry for entry in provider_settings if entry.provider == provider]
        if len(matches) > 1:
            raise ValueError(f"Duplicate provider_settings entries supplied for provider '{provider}'.")
        return matches[0] if matches else None

    @staticmethod
    def _reference_sort_key(reference) -> tuple:
        hierarchy = reference.document_hierarchy or []
        hierarchy_key = tuple((entry.heading_level, entry.order, entry.heading_number or "", entry.title or "") for entry in hierarchy)
        return str(reference.guideline_id), hierarchy_key, str(reference.id)

    def _get_guideline_cached(self, guideline_id: str, guideline_cache: Dict[str, Any]):
        if guideline_id not in guideline_cache:
            guideline_cache[guideline_id] = self.guideline_service.get_guideline_by_id(guideline_id)
        return guideline_cache[guideline_id]

    @staticmethod
    def _extract_reference_content(reference, metadata_content_mode: MetadataContentMode) -> Optional[str]:
        if reference.type == ReferenceType.TEXT:
            return reference.contained_text
        if reference.type == ReferenceType.IMAGE:
            return " ".join(part for part in [reference.caption, reference.describing_text] if part).strip() or None
        if reference.type == ReferenceType.TABLE:
            return " ".join(part for part in [reference.caption, reference.plain_text] if part).strip() or None
        if reference.type == ReferenceType.RECOMMENDATION:
            return " ".join(part for part in [reference.recommendation_title, reference.recommendation_content] if part).strip() or None
        if reference.type == ReferenceType.STATEMENT:
            return " ".join(part for part in [reference.statement_title, reference.statement_content] if part).strip() or None
        if reference.type == ReferenceType.METADATA:
            if metadata_content_mode == MetadataContentMode.SKIP_HEADING_METADATA and "Heading" in (reference.metadata_type or ""):
                return None
            return reference.metadata_content
        raise ValueError(f"Unknown reference type: {reference.type}")

    @staticmethod
    def _map_property_value(mapped_field: VectorCollectionMappedField, reference, guideline) -> Optional[str]:
        if mapped_field == VectorCollectionMappedField.REFERENCE_TYPE:
            return reference.type.value
        if mapped_field == VectorCollectionMappedField.HEADERS:
            parts = []
            for entry in sorted(reference.document_hierarchy or [], key=lambda item: item.heading_level):
                number = (entry.heading_number or "").strip()
                title = (entry.title or "").strip()
                combined = " ".join(part for part in [number, title] if part).strip()
                if combined:
                    parts.append(combined)
            return " / ".join(parts) or None
        if mapped_field == VectorCollectionMappedField.GUIDELINE_TITLE:
            register = (guideline.awmf_register_number or "").strip()
            title = (guideline.title or "").strip()
            return " ".join(part for part in [register, title] if part).strip() or None
        if mapped_field == VectorCollectionMappedField.GUIDELINE_KEYWORDS:
            values = list(guideline.keywords or [])
            values.extend([guideline.goal, guideline.target_patients, guideline.care_area])
            return "; ".join(value for value in values if value) or None
        if mapped_field == VectorCollectionMappedField.REFERENCE_KEYWORDS:
            return "; ".join(reference.associated_keywords or []) or None
        raise ValueError(f"Unsupported mapped field: {mapped_field}")

    def _get_client(self):
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    @staticmethod
    def _fetch_objects_by_guideline(client_collection, guideline_id: str):
        try:
            from weaviate.collections.classes.filters import Filter
            filters = Filter.by_property("guideline_id").equal(str(guideline_id))
        except ImportError:
            filters = SimpleNamespace(target=SimpleNamespace(value=str(guideline_id)))

        return client_collection.query.fetch_objects(
            filters=filters,
        ).objects or []

    @staticmethod
    def _metadata_query(**kwargs):
        from weaviate.classes.query import MetadataQuery

        return MetadataQuery(**kwargs)

    @staticmethod
    def _create_weaviate_collection(client, request: CreateWeaviateCollectionRequest) -> None:
        from weaviate.classes.config import Configure, Property, VectorDistances

        properties = [
            Property(
                name=property_schema.name,
                data_type=WeaviateVectorStoreService._to_weaviate_data_type(property_schema.data_type),
                description=property_schema.description,
            )
            for property_schema in request.properties
        ]
        vectorizer_config = [
            Configure.NamedVectors.none(
                name=named_vector.name,
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances(named_vector.distance_metric),
                ),
            )
            for named_vector in request.named_vectors
        ]
        client.collections.create(
            name=request.name,
            description=request.description,
            properties=properties,
            vectorizer_config=vectorizer_config,
        )

    @staticmethod
    def _to_weaviate_data_type(data_type: str):
        from weaviate.classes.config import DataType

        try:
            return getattr(DataType, WEAVIATE_DATA_TYPE_MEMBER_MAP[data_type])
        except KeyError as exc:
            raise ValueError(f"Unsupported Weaviate property data_type: {data_type}") from exc

    @staticmethod
    def _build_client():
        try:
            import weaviate
        except ImportError as exc:
            raise RuntimeError("Install the 'weaviate-client' package to use the Weaviate endpoints.") from exc

        weaviate_url = os.getenv("WEAVIATE_URL", "http://127.0.0.1:8080")
        grpc_url = os.getenv("WEAVIATE_GRPC_URL", "http://127.0.0.1:50051")
        http_parsed = urlparse(weaviate_url)
        grpc_parsed = urlparse(grpc_url)

        client = weaviate.connect_to_custom(
            http_host=http_parsed.hostname,
            http_port=http_parsed.port,
            http_secure=http_parsed.scheme == "https",
            grpc_host=grpc_parsed.hostname,
            grpc_port=grpc_parsed.port,
            grpc_secure=grpc_parsed.scheme == "https",
        )
        client.connect()
        return client
