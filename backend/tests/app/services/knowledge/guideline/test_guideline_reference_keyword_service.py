import copy
import importlib.util
import sys
import types
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))


class FakeObjectId(str):
    def __new__(cls, value=None):
        return str.__new__(cls, value or uuid.uuid4().hex[:24])

    @staticmethod
    def is_valid(value):
        return isinstance(value, str) and len(value) == 24


fake_bson_module = types.ModuleType("bson")
fake_bson_module.ObjectId = FakeObjectId
sys.modules.setdefault("bson", fake_bson_module)

fake_pymongo_module = types.ModuleType("pymongo")
fake_pymongo_collection_module = types.ModuleType("pymongo.collection")
fake_pymongo_collection_module.Collection = object
fake_pymongo_module.collection = fake_pymongo_collection_module
sys.modules.setdefault("pymongo", fake_pymongo_module)
sys.modules.setdefault("pymongo.collection", fake_pymongo_collection_module)

sys.modules.setdefault("yake", types.SimpleNamespace(KeywordExtractor=None))
sys.modules.setdefault("litellm", types.SimpleNamespace(completion=None))

from bson import ObjectId

from app.models.knowledge.guideline import (  # noqa: E402
    KeywordExtractionStrategy,
    ReferenceKeywordEnrichmentRequest,
    ReferenceKeywordExpansionSettings,
    ReferenceKeywordSettings,
    ReferenceType,
)
from app.models.tools.llm_interaction import LLMSettings  # noqa: E402
from app.models.tools.snomed_interaction import SnomedKeywordExpansionItem, SnomedSettings  # noqa: E402

_REFERENCE_SERVICE_PATH = Path(__file__).resolve().parents[5] / "src" / "app" / "services" / "knowledge" / "guideline" / "guideline_reference_service.py"
_REFERENCE_SERVICE_SPEC = importlib.util.spec_from_file_location("test_guideline_reference_service_module", _REFERENCE_SERVICE_PATH)
_REFERENCE_SERVICE_MODULE = importlib.util.module_from_spec(_REFERENCE_SERVICE_SPEC)
assert _REFERENCE_SERVICE_SPEC is not None and _REFERENCE_SERVICE_SPEC.loader is not None
_REFERENCE_SERVICE_SPEC.loader.exec_module(_REFERENCE_SERVICE_MODULE)
GuidelineReferenceService = _REFERENCE_SERVICE_MODULE.GuidelineReferenceService

_KEYWORD_SERVICE_PATH = Path(__file__).resolve().parents[5] / "src" / "app" / "services" / "knowledge" / "guideline" / "guideline_reference_keyword_service.py"
_KEYWORD_SERVICE_SPEC = importlib.util.spec_from_file_location("test_guideline_reference_keyword_service_module", _KEYWORD_SERVICE_PATH)
_KEYWORD_SERVICE_MODULE = importlib.util.module_from_spec(_KEYWORD_SERVICE_SPEC)
assert _KEYWORD_SERVICE_SPEC is not None and _KEYWORD_SERVICE_SPEC.loader is not None
_KEYWORD_SERVICE_SPEC.loader.exec_module(_KEYWORD_SERVICE_MODULE)
GuidelineReferenceKeywordService = _KEYWORD_SERVICE_MODULE.GuidelineReferenceKeywordService


class InMemoryCollection:
    def __init__(self, documents=None):
        self.documents = [copy.deepcopy(document) for document in (documents or [])]

    def find_one(self, query, projection=None, sort=None):
        docs = self.find(query, projection=None)
        if sort:
            for field, direction in reversed(sort):
                docs.sort(key=lambda doc: doc.get(field), reverse=direction < 0)
        if not docs:
            return None
        return self._apply_projection(copy.deepcopy(docs[0]), projection)

    def find(self, query=None, projection=None):
        query = query or {}
        results = [copy.deepcopy(document) for document in self.documents if self._matches(document, query)]
        return [self._apply_projection(document, projection) for document in results]

    def insert_one(self, payload):
        document = copy.deepcopy(payload)
        document.setdefault("_id", ObjectId())
        self.documents.append(document)
        return SimpleNamespace(inserted_id=document["_id"])

    def update_one(self, query, update):
        matched_count = 0
        for document in self.documents:
            if self._matches(document, query):
                matched_count += 1
                document.update(copy.deepcopy(update.get("$set", {})))
                break
        return SimpleNamespace(matched_count=matched_count)

    def delete_one(self, query):
        deleted_count = 0
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                del self.documents[index]
                deleted_count = 1
                break
        return SimpleNamespace(deleted_count=deleted_count)

    def delete_many(self, query):
        remaining_documents = []
        deleted_count = 0
        for document in self.documents:
            if self._matches(document, query):
                deleted_count += 1
            else:
                remaining_documents.append(document)
        self.documents = remaining_documents
        return SimpleNamespace(deleted_count=deleted_count)

    @staticmethod
    def _apply_projection(document, projection):
        if not projection:
            return document
        include_fields = {field for field, include in projection.items() if include}
        if not include_fields:
            return document
        projected = {field: document[field] for field in include_fields if field in document}
        if "_id" in document and ("_id" in include_fields or "_id" not in projection):
            projected["_id"] = document["_id"]
        return projected

    @staticmethod
    def _matches(document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(InMemoryCollection._matches(document, branch) for branch in value):
                    return False
                continue
            if document.get(key) != value:
                return False
        return True


class FakeKeywordService:
    def __init__(self):
        self.yake_calls = []
        self.llm_calls = []

    def extract_yake(self, **kwargs):
        self.yake_calls.append(kwargs)
        return ["weisheitszahn", "retention"]

    def extract_llm(self, text, **kwargs):
        self.llm_calls.append({"text": text, **kwargs})
        return ["operative entfernung", "weisheitszahn"]


class FakeSnomedService:
    def __init__(self):
        self.calls = []

    def expand_keywords(self, keywords, **kwargs):
        self.calls.append({"keywords": keywords, **kwargs})
        return [
            SnomedKeywordExpansionItem(
                keyword="weisheitszahn",
                canonical_form="Weisheitszahn",
                expanded_terms=["weisheitszahn", "dritter molar"],
            ),
            SnomedKeywordExpansionItem(
                keyword="operative entfernung",
                canonical_form="Operative Entfernung",
                expanded_terms=["operative entfernung"],
            ),
        ]


class GuidelineReferenceKeywordServiceTest(unittest.TestCase):
    def setUp(self):
        self.guideline_id = ObjectId()
        self.other_guideline_id = ObjectId()
        self.group_id = ObjectId()
        self.reference_id = ObjectId()
        self.other_reference_id = ObjectId()

        self.guideline_collection = InMemoryCollection(
            [
                {"_id": self.guideline_id, "title": "Guideline A"},
                {"_id": self.other_guideline_id, "title": "Guideline B"},
            ],
        )
        self.reference_groups_collection = InMemoryCollection(
            [{"_id": self.group_id, "name": "group-a"}],
        )
        self.reference_collection = InMemoryCollection(
            [
                {
                    "_id": self.reference_id,
                    "reference_group_id": self.group_id,
                    "guideline_id": self.guideline_id,
                    "type": ReferenceType.TEXT.value,
                    "contained_text": "Weisheitszahn operative Entfernung",
                    "bboxs": [],
                    "document_hierarchy": [],
                    "created_automatically": True,
                },
                {
                    "_id": self.other_reference_id,
                    "reference_group_id": self.group_id,
                    "guideline_id": self.other_guideline_id,
                    "type": ReferenceType.TEXT.value,
                    "contained_text": "Andere Leitlinie",
                    "bboxs": [],
                    "document_hierarchy": [],
                    "created_automatically": True,
                },
            ],
        )

        self.reference_service = GuidelineReferenceService(
            guideline_collection=self.guideline_collection,
            reference_groups_collection=self.reference_groups_collection,
            reference_collection=self.reference_collection,
        )
        self.keyword_service = FakeKeywordService()
        self.snomed_service = FakeSnomedService()
        self.service = GuidelineReferenceKeywordService(
            reference_service=self.reference_service,
            keyword_service=self.keyword_service,
            snomed_service=self.snomed_service,
        )

    def test_enriches_single_reference_with_yake(self):
        result = self.service.enrich_keywords(
            ReferenceKeywordEnrichmentRequest(
                reference_id=self.reference_id,
                keyword_settings=ReferenceKeywordSettings(
                    strategy=KeywordExtractionStrategy.YAKE,
                    max_keywords=5,
                ),
            ),
        )

        self.assertEqual(result.processed_reference_count, 1)
        self.assertEqual(result.references[0].stored_keywords, ["weisheitszahn", "retention"])
        updated_reference = self.reference_service.get_reference_by_id(self.reference_id)
        self.assertEqual(updated_reference.associated_keywords, ["weisheitszahn", "retention"])
        self.assertEqual(len(self.keyword_service.yake_calls), 1)

    def test_enriches_group_restricted_to_one_guideline_and_expands_keywords(self):
        result = self.service.enrich_keywords(
            ReferenceKeywordEnrichmentRequest(
                reference_group_id=self.group_id,
                guideline_id=self.guideline_id,
                keyword_settings=ReferenceKeywordSettings(
                    strategy=KeywordExtractionStrategy.LLM,
                    llm_settings=LLMSettings(model="fake-model"),
                ),
                expansion_settings=ReferenceKeywordExpansionSettings(
                    enabled=True,
                    snomed_settings=SnomedSettings(),
                ),
            ),
        )

        self.assertEqual(result.processed_reference_count, 1)
        self.assertEqual(
            result.references[0].stored_keywords,
            ["weisheitszahn", "dritter molar", "operative entfernung"],
        )
        updated_reference = self.reference_service.get_reference_by_id(self.reference_id)
        untouched_reference = self.reference_service.get_reference_by_id(self.other_reference_id)
        self.assertEqual(updated_reference.associated_keywords, ["weisheitszahn", "dritter molar", "operative entfernung"])
        self.assertIsNone(untouched_reference.associated_keywords)
        self.assertEqual(len(self.snomed_service.calls), 1)


if __name__ == "__main__":
    unittest.main()
