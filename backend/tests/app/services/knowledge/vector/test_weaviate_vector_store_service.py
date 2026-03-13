import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

from app.models.knowledge.guideline import GuidelineMetadataReference, GuidelineHierarchyEntry, ReferenceType  # noqa: E402
from app.models.knowledge.vector import CreateWeaviateCollectionRequest, DeleteGuidelineResponse, IngestGuidelineRequest, IngestReferenceGroupResponse, MetadataContentMode, VectorCollectionIngestionMapping, VectorCollectionMappedField, WeaviateCollectionProperty, WeaviateNamedVector, WeaviateSearchMode, WeaviateSearchRequest  # noqa: E402
from app.services.knowledge.vector import WeaviateVectorStoreService  # noqa: E402


class InMemoryCollection:
    def __init__(self):
        self.documents = []

    def find(self, query=None, projection=None):
        query = query or {}
        result = []
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                result.append(self._project(document, projection))
        return result

    def find_one(self, query, projection=None):
        matches = self.find(query, projection)
        return matches[0] if matches else None

    def update_one(self, query, update, upsert=False):
        existing = self.find_one(query)
        if existing is None:
            if not upsert:
                return
            document = dict(query)
            document.update(update.get("$set", {}))
            self.documents.append(document)
            return
        existing.update(update.get("$set", {}))
        for index, document in enumerate(self.documents):
            if all(document.get(key) == value for key, value in query.items()):
                self.documents[index] = existing
                return

    def delete_one(self, query):
        self.documents = [
            document for document in self.documents if not all(document.get(key) == value for key, value in query.items())
        ]

    @staticmethod
    def _project(document, projection):
        if not projection:
            return dict(document)
        include_fields = [field for field, include in projection.items() if include]
        if not include_fields:
            return dict(document)
        return {field: document[field] for field in include_fields if field in document}


class FakeEmbeddingService:
    def __init__(self):
        self.calls = []

    def get_vectorizer(self, provider):
        return SimpleNamespace(provider=provider)

    def embed_texts(self, provider, texts, *, provider_settings=None, purpose, normalize=False):
        self.calls.append(
            {
                "provider": provider,
                "texts": list(texts),
                "provider_settings": provider_settings,
                "purpose": purpose,
                "normalize": normalize,
            },
        )
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeCollectionData:
    def __init__(self):
        self.inserts = []
        self.deleted_ids = []

    def insert(self, properties, vector):
        self.inserts.append({"properties": properties, "vector": vector})
        return "uuid-1"

    def delete_by_id(self, object_id):
        self.deleted_ids.append(object_id)


class FakeCollectionQuery:
    def __init__(self, data):
        self.data = data

    def near_vector(self, **kwargs):
        return SimpleNamespace(
            objects=[
                SimpleNamespace(
                    uuid="uuid-1",
                    properties={"title": "Test"},
                    metadata=SimpleNamespace(score=0.91, distance=0.09),
                ),
            ],
        )

    def hybrid(self, **kwargs):
        return self.near_vector(**kwargs)

    def fetch_objects(self, filters=None, **kwargs):
        object_list = []
        for index, item in enumerate(self.data.inserts):
            properties = item["properties"]
            if filters is not None:
                value = getattr(filters.target, "value", None)
                if properties.get("guideline_id") != value:
                    continue
            object_list.append(
                SimpleNamespace(
                    uuid=f"uuid-{index + 1}",
                    properties=properties,
                    metadata=SimpleNamespace(score=None, distance=None),
                ),
            )
        return SimpleNamespace(objects=object_list)


class FakeClientCollection:
    def __init__(self):
        self.data = FakeCollectionData()
        self.query = FakeCollectionQuery(self.data)


class FakeCollectionsManager:
    def __init__(self):
        self.created = []
        self.deleted = []
        self.exists_names = set()
        self.named = {}

    def create(self, **kwargs):
        self.created.append(kwargs)
        self.exists_names.add(kwargs["name"])
        self.named[kwargs["name"]] = FakeClientCollection()

    def exists(self, name):
        return name in self.exists_names

    def delete(self, name):
        self.deleted.append(name)
        self.exists_names.discard(name)
        self.named.pop(name, None)

    def get(self, name):
        return self.named[name]


class FakeWeaviateClient:
    def __init__(self):
        self.collections = FakeCollectionsManager()


class FakeGuidelineService:
    def get_guideline_by_id(self, guideline_id):
        return SimpleNamespace(
            awmf_register_number="007-001",
            title="Guideline A",
            keywords=["alpha", "beta"],
            goal="goal",
            target_patients="patients",
            care_area="care",
        )


class FakeGuidelineReferenceService:
    def __init__(self, references=None):
        self.references = references or []

    def list_references(self, reference_group_id=None, guideline_id=None):
        results = list(self.references)
        if guideline_id is not None:
            results = [reference for reference in results if str(reference.guideline_id) == str(guideline_id)]
        return results


class WeaviateVectorStoreServiceTest(unittest.TestCase):
    def setUp(self):
        self.metadata_collection = InMemoryCollection()
        self.embedding_service = FakeEmbeddingService()
        self.weaviate_client = FakeWeaviateClient()
        self.service = WeaviateVectorStoreService(
            metadata_collection=self.metadata_collection,
            embedding_service=self.embedding_service,
            guideline_service=FakeGuidelineService(),
            guideline_reference_service=FakeGuidelineReferenceService(),
            client_factory=lambda: self.weaviate_client,
        )
        self.service._create_weaviate_collection = lambda client, request: client.collections.create(name=request.name)

        self.collection_request = CreateWeaviateCollectionRequest(
            name="GuidelineChunks",
            reference_group_id=ObjectId(),
            description="Chunk storage",
            properties=[
                WeaviateCollectionProperty(name="title", data_type="text"),
                WeaviateCollectionProperty(name="body", data_type="text"),
                WeaviateCollectionProperty(name="text", data_type="text"),
                WeaviateCollectionProperty(name="chunk_index", data_type="int"),
                WeaviateCollectionProperty(name="guideline_id", data_type="text"),
                WeaviateCollectionProperty(name="reference_id", data_type="text"),
                WeaviateCollectionProperty(name="reference_type", data_type="text"),
                WeaviateCollectionProperty(name="headers", data_type="text"),
                WeaviateCollectionProperty(name="guideline_title", data_type="text"),
                WeaviateCollectionProperty(name="guideline_keywords", data_type="text"),
                WeaviateCollectionProperty(name="reference_keywords", data_type="text"),
            ],
            named_vectors=[
                WeaviateNamedVector(name="body_vector", source_property="text", provider="fake"),
            ],
            ingestion_mapping=VectorCollectionIngestionMapping(
                content_property="text",
                mapped_properties={
                    "reference_type": VectorCollectionMappedField.REFERENCE_TYPE,
                    "headers": VectorCollectionMappedField.HEADERS,
                    "guideline_title": VectorCollectionMappedField.GUIDELINE_TITLE,
                    "guideline_keywords": VectorCollectionMappedField.GUIDELINE_KEYWORDS,
                    "reference_keywords": VectorCollectionMappedField.REFERENCE_KEYWORDS,
                },
                metadata_content_mode=MetadataContentMode.SKIP_HEADING_METADATA,
            ),
        )

    def test_create_collection_persists_metadata(self):
        created = self.service.create_collection(self.collection_request)

        self.assertEqual(created.name, "GuidelineChunks")
        self.assertEqual(len(self.metadata_collection.documents), 1)
        self.assertTrue(self.weaviate_client.collections.exists("GuidelineChunks"))

    def test_property_data_type_is_normalized_and_mapped_for_weaviate(self):
        normalized_property = WeaviateCollectionProperty(name="score", data_type=" Number[] ")

        self.assertEqual(normalized_property.data_type, "number[]")
        self.assertEqual(
            WeaviateVectorStoreService.WEAVIATE_DATA_TYPE_MEMBER_MAP[normalized_property.data_type],
            "NUMBER_ARRAY",
        )

    def test_insert_object_vectorizes_named_vector_properties(self):
        self.service.create_collection(self.collection_request)

        result = self.service.insert_object(
            "GuidelineChunks",
            {"title": "A", "body": "Vector me", "text": "Vector me"},
        )

        self.assertEqual(result.uuid, "uuid-1")
        self.assertEqual(self.embedding_service.calls[0]["provider"], "fake")
        inserted = self.weaviate_client.collections.get("GuidelineChunks").data.inserts[0]
        self.assertEqual(inserted["vector"]["body_vector"], [0.1, 0.2, 0.3])

    def test_search_embeds_query_and_returns_hits(self):
        self.service.create_collection(self.collection_request)
        self.service._metadata_query = lambda **kwargs: kwargs

        response = self.service.search(
            "GuidelineChunks",
            WeaviateSearchRequest(
                query="appendix carcinoma",
                vector_name="body_vector",
                mode=WeaviateSearchMode.VECTOR,
            ),
        )

        self.assertEqual(response.collection_name, "GuidelineChunks")
        self.assertEqual(len(response.hits), 1)
        self.assertEqual(self.embedding_service.calls[-1]["texts"], ["appendix carcinoma"])

    def test_ingest_reference_group_maps_reference_and_guideline_metadata(self):
        reference = GuidelineMetadataReference(
            _id=ObjectId(),
            reference_group_id=self.collection_request.reference_group_id,
            guideline_id=ObjectId(),
            metadata_type="Info",
            metadata_content="Contained metadata",
            associated_keywords=["kw1", "kw2"],
            document_hierarchy=[
                GuidelineHierarchyEntry(title="Kapitel", heading_level=1, heading_number="1", order=0),
                GuidelineHierarchyEntry(title="Abschnitt", heading_level=2, heading_number="1.1", order=1),
            ],
        )
        self.service.guideline_reference_service = FakeGuidelineReferenceService([reference])
        self.service.create_collection(self.collection_request)

        result = self.service.ingest_reference_group("GuidelineChunks")

        self.assertIsInstance(result, IngestReferenceGroupResponse)
        self.assertEqual(result.inserted_object_count, 1)
        inserted = self.weaviate_client.collections.get("GuidelineChunks").data.inserts[0]["properties"]
        self.assertEqual(inserted["text"], "Contained metadata")
        self.assertEqual(inserted["chunk_index"], 0)
        self.assertEqual(inserted["reference_type"], ReferenceType.METADATA.value)
        self.assertEqual(inserted["headers"], "1 Kapitel / 1.1 Abschnitt")
        self.assertEqual(inserted["guideline_title"], "007-001 Guideline A")
        self.assertEqual(inserted["guideline_keywords"], "alpha; beta; goal; patients; care")
        self.assertEqual(inserted["reference_keywords"], "kw1; kw2")

    def test_ingest_reference_group_skips_heading_metadata_when_configured(self):
        reference = GuidelineMetadataReference(
            _id=ObjectId(),
            reference_group_id=self.collection_request.reference_group_id,
            guideline_id=ObjectId(),
            metadata_type="Heading (level 2)",
            metadata_content="Ignored heading",
        )
        self.service.guideline_reference_service = FakeGuidelineReferenceService([reference])
        self.service.create_collection(self.collection_request)

        result = self.service.ingest_reference_group("GuidelineChunks")

        self.assertEqual(result.inserted_object_count, 0)
        self.assertEqual(len(result.skipped_reference_ids), 1)

    def test_upsert_guideline_recreates_only_one_guideline_with_local_chunk_indices(self):
        guideline_id = ObjectId()
        references = [
            GuidelineMetadataReference(
                _id=ObjectId(),
                reference_group_id=self.collection_request.reference_group_id,
                guideline_id=guideline_id,
                metadata_type="Info",
                metadata_content="First",
            ),
            GuidelineMetadataReference(
                _id=ObjectId(),
                reference_group_id=self.collection_request.reference_group_id,
                guideline_id=guideline_id,
                metadata_type="Info",
                metadata_content="Second",
            ),
        ]
        self.service.guideline_reference_service = FakeGuidelineReferenceService(references)
        self.service.create_collection(self.collection_request)
        collection = self.weaviate_client.collections.get("GuidelineChunks")
        collection.data.insert(
            {"guideline_id": str(guideline_id), "reference_id": "old", "chunk_index": 77, "text": "old"},
            {"body_vector": [0.1]},
        )
        collection.data.insert(
            {"guideline_id": "other", "reference_id": "keep", "chunk_index": 0, "text": "keep"},
            {"body_vector": [0.1]},
        )

        result = self.service.upsert_guideline(
            "GuidelineChunks",
            str(guideline_id),
            IngestGuidelineRequest(),
        )

        self.assertEqual(result.inserted_object_count, 2)
        inserted_props = [item["properties"] for item in collection.data.inserts if item["properties"]["guideline_id"] == str(guideline_id)]
        self.assertEqual([item["chunk_index"] for item in inserted_props[-2:]], [0, 1])
        self.assertIn("uuid-1", collection.data.deleted_ids)

    def test_ingest_reference_group_can_replace_one_guideline_when_guideline_id_is_provided(self):
        guideline_id = ObjectId()
        references = [
            GuidelineMetadataReference(
                _id=ObjectId(),
                reference_group_id=self.collection_request.reference_group_id,
                guideline_id=guideline_id,
                metadata_type="Info",
                metadata_content="Only guideline content",
            ),
            GuidelineMetadataReference(
                _id=ObjectId(),
                reference_group_id=self.collection_request.reference_group_id,
                guideline_id=ObjectId(),
                metadata_type="Info",
                metadata_content="Other guideline content",
            ),
        ]
        self.service.guideline_reference_service = FakeGuidelineReferenceService(references)
        self.service.create_collection(self.collection_request)

        result = self.service.ingest_reference_group("GuidelineChunks", guideline_id=str(guideline_id))

        self.assertEqual(result.inserted_object_count, 1)
        inserted_props = self.weaviate_client.collections.get("GuidelineChunks").data.inserts[-1]["properties"]
        self.assertEqual(inserted_props["guideline_id"], str(guideline_id))
        self.assertEqual(inserted_props["chunk_index"], 0)

    def test_delete_guideline_objects_returns_deleted_count(self):
        guideline_id = "guideline-1"
        self.service.create_collection(self.collection_request)
        collection = self.weaviate_client.collections.get("GuidelineChunks")
        collection.data.insert({"guideline_id": guideline_id, "reference_id": "r1", "text": "a"}, {"body_vector": [0.1]})
        collection.data.insert({"guideline_id": guideline_id, "reference_id": "r2", "text": "b"}, {"body_vector": [0.1]})
        collection.data.insert({"guideline_id": "other", "reference_id": "r3", "text": "c"}, {"body_vector": [0.1]})

        result = self.service.delete_guideline_objects("GuidelineChunks", guideline_id)

        self.assertIsInstance(result, DeleteGuidelineResponse)
        self.assertEqual(result.deleted_object_count, 2)


if __name__ == "__main__":
    unittest.main()
