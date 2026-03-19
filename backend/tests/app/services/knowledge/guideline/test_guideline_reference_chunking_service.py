import copy
import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

from app.models.knowledge.guideline import (  # noqa: E402
    ChunkingStrategy,
    GuidelineDownloadInformation,
    GuidelineEntry,
    GuidelineValidityInformation,
    GuidelineReferenceChunkingRequest,
    GuidelineReferenceChunkingUpdateRequest,
    OrganizationEntry,
    ReferenceType,
)
from app.services.knowledge.guideline import GuidelineReferenceChunkingService, GuidelineReferenceService  # noqa: E402


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


class FakeGuidelineService:
    def __init__(self, guidelines):
        self.guidelines = {str(guideline.id): guideline for guideline in guidelines}
    
    def get_guideline_by_id(self, guideline_id):
        return self.guidelines[str(guideline_id)]


class FakeBoundingBoxFinderService:
    def __init__(self):
        self.calls = []
    
    def text_to_bounding_boxes(self, guideline, text, start_page=None, end_page=None):
        self.calls.append(
            {
                "guideline_id": guideline.id,
                "text": text,
                "start_page": start_page,
                "end_page": end_page,
            },
        )
        return [{"page": start_page or 1, "positions": [1.0, 2.0, 3.0, 4.0]}]


class GuidelineReferenceChunkingServiceTest(unittest.TestCase):
    def setUp(self):
        self.guideline_id = ObjectId()
        self.other_guideline_id = ObjectId()
        self.source_group_id = ObjectId()
        self.second_source_group_id = ObjectId()
        self.target_group_id = ObjectId()
        
        self.reference_groups_collection = InMemoryCollection(
            [
                {"_id": self.source_group_id, "name": "source_group"},
                {"_id": self.second_source_group_id, "name": "source_group_v2"},
                {"_id": self.target_group_id, "name": "chunked_target"},
            ],
        )
        self.guideline_collection = InMemoryCollection(
            [
                {"_id": self.guideline_id, "title": "Guideline A"},
                {"_id": self.other_guideline_id, "title": "Guideline B"},
            ],
        )
        self.reference_collection = InMemoryCollection(
            [
                self._reference(
                    self.source_group_id,
                    self.guideline_id,
                    ReferenceType.METADATA.value,
                    0,
                    metadata_type="Heading (level 2)",
                    metadata_content="12.2",
                ),
                self._reference(self.source_group_id, self.guideline_id, ReferenceType.TEXT.value, 1, contained_text="abcdefghij"),
                self._reference(
                    self.source_group_id, self.guideline_id, ReferenceType.TABLE.value, 2, caption="Tabelle 3", plain_text="row",
                    table_markdown="|a|",
                ),
                self._reference(
                    self.second_source_group_id,
                    self.guideline_id,
                    ReferenceType.TEXT.value,
                    0,
                    contained_text="Erster Satz. Zweiter Satz. Dritter Satz.",
                ),
                self._reference(
                    self.second_source_group_id,
                    self.guideline_id,
                    ReferenceType.TABLE.value,
                    1,
                    caption="Tabelle Neu",
                    plain_text="row",
                    table_markdown="|b|",
                ),
                self._reference(
                    self.target_group_id,
                    self.guideline_id,
                    ReferenceType.TEXT.value,
                    0,
                    contained_text="old chunk",
                ),
                self._reference(
                    self.target_group_id,
                    self.other_guideline_id,
                    ReferenceType.TEXT.value,
                    0,
                    contained_text="leave me alone",
                ),
            ],
        )
        
        self.reference_service = GuidelineReferenceService(
            guideline_collection=self.guideline_collection,
            reference_groups_collection=self.reference_groups_collection,
            reference_collection=self.reference_collection,
        )
        self.fake_guideline_service = FakeGuidelineService(
            [
                self._guideline(self.guideline_id, "007-001"),
                self._guideline(self.other_guideline_id, "007-002"),
            ],
        )
        self.fake_bounding_box_finder_service = FakeBoundingBoxFinderService()
        self.chunking_service = GuidelineReferenceChunkingService(
            reference_service=self.reference_service,
            guideline_service=self.fake_guideline_service,
            bounding_box_finder_service=self.fake_bounding_box_finder_service,
        )
    
    def test_create_chunked_reference_group_reindexes_following_siblings(self):
        result = self.chunking_service.create_chunked_reference_group(
            GuidelineReferenceChunkingRequest(
                source_reference_group_id=self.source_group_id,
                chunking_strategy=ChunkingStrategy.FIXED_CHARACTERS,
                fixed_character_amount=5,
            ),
        )
        
        created_references = self.reference_service.list_references(reference_group_id=result.target_reference_group_id)
        created_references = sorted(
            created_references,
            key=lambda reference: tuple(entry.order for entry in reference.document_hierarchy),
        )
        created_group = self.reference_service.get_reference_group_by_id(result.target_reference_group_id)
        self.assertEqual(result.chunked_text_reference_count, 1)
        self.assertEqual(result.created_reference_count, 4)
        self.assertTrue(created_group.is_chunking_result)
        self.assertEqual(
            [reference.type for reference in created_references], [
                ReferenceType.METADATA,
                ReferenceType.TEXT,
                ReferenceType.TEXT,
                ReferenceType.TABLE,
            ],
        )
        self.assertEqual(
            [reference.document_hierarchy[-1].order for reference in created_references],
            [0, 1, 2, 3],
        )
        self.assertEqual(
            [reference.contained_text for reference in created_references if reference.type == ReferenceType.TEXT],
            ["abcde", "fghij"],
        )
        self.assertEqual(
            [call["text"] for call in self.fake_bounding_box_finder_service.calls],
            ["abcde", "fghij"],
        )
        self.assertTrue(all(call["start_page"] == 33 and call["end_page"] == 33 for call in self.fake_bounding_box_finder_service.calls))
    
    def test_sentence_chunking_splits_each_sentence(self):
        result = self.chunking_service.create_chunked_reference_group(
            GuidelineReferenceChunkingRequest(
                source_reference_group_id=self.second_source_group_id,
                chunking_strategy=ChunkingStrategy.SENTENCE,
            ),
        )
        
        created_references = self.reference_service.list_references(reference_group_id=result.target_reference_group_id)
        created_references = sorted(
            created_references,
            key=lambda reference: tuple(entry.order for entry in reference.document_hierarchy),
        )
        created_texts = [reference.contained_text for reference in created_references if reference.type == ReferenceType.TEXT]
        self.assertEqual(
            created_texts,
            ["Erster Satz.", "Zweiter Satz.", "Dritter Satz."],
        )
        self.assertEqual(
            [reference.document_hierarchy[-1].order for reference in created_references],
            [0, 1, 2, 3],
        )
        self.assertEqual(
            [call["text"] for call in self.fake_bounding_box_finder_service.calls],
            ["Erster Satz.", "Zweiter Satz.", "Dritter Satz."],
        )
    
    def test_fixed_character_chunking_does_not_cut_last_word(self):
        chunks = self.chunking_service._split_text_reference(
            "Alpha Beta Gamma",
            strategy=ChunkingStrategy.FIXED_CHARACTERS,
            fixed_character_amount=12,
        )
        
        self.assertEqual(chunks, ["Alpha Beta", "Gamma"])
    
    def test_update_chunked_guideline_replaces_only_selected_guideline(self):
        result = self.chunking_service.update_chunked_guideline(
            GuidelineReferenceChunkingUpdateRequest(
                source_reference_group_id=self.second_source_group_id,
                target_reference_group_id=self.target_group_id,
                guideline_id=self.guideline_id,
                chunking_strategy=ChunkingStrategy.SENTENCE,
            ),
        )
        
        target_references = self.reference_service.list_references(reference_group_id=self.target_group_id)
        updated_guideline_references = [
            reference for reference in target_references if reference.guideline_id == self.guideline_id
        ]
        updated_guideline_references = sorted(
            updated_guideline_references,
            key=lambda reference: tuple(entry.order for entry in reference.document_hierarchy),
        )
        untouched_guideline_references = [
            reference for reference in target_references if reference.guideline_id == self.other_guideline_id
        ]
        
        self.assertEqual(len(result.deleted_reference_ids), 1)
        self.assertEqual(
            [reference.contained_text for reference in updated_guideline_references if reference.type == ReferenceType.TEXT],
            ["Erster Satz.", "Zweiter Satz.", "Dritter Satz."],
        )
        self.assertEqual(
            [reference.document_hierarchy[-1].order for reference in updated_guideline_references],
            [0, 1, 2, 3],
        )
        self.assertEqual(len(untouched_guideline_references), 1)
        self.assertEqual(untouched_guideline_references[0].contained_text, "leave me alone")
        self.assertEqual(
            [call["text"] for call in self.fake_bounding_box_finder_service.calls],
            ["Erster Satz.", "Zweiter Satz.", "Dritter Satz."],
        )
    
    @staticmethod
    def _reference(reference_group_id, guideline_id, reference_type, order, **content_fields):
        payload = {
            "_id": ObjectId(),
            "reference_group_id": reference_group_id,
            "guideline_id": guideline_id,
            "type": reference_type,
            "bboxs": [{"page": 33, "positions": [70.0, 200.0 + order, 350.0, 220.0 + order]}],
            "document_hierarchy": [
                {"title": "Root", "heading_level": 0, "heading_number": "", "order": 0},
                {"title": "Kapitel", "heading_level": 1, "heading_number": "12", "order": 17},
                {"title": "Abschnitt", "heading_level": 2, "heading_number": "12.2", "order": 2},
                {"title": "", "heading_level": 3, "heading_number": "", "order": order},
            ],
            "created_automatically": True,
        }
        payload.update(content_fields)
        return payload
    
    @staticmethod
    def _guideline(guideline_id, register_number):
        return GuidelineEntry(
            _id=guideline_id,
            awmf_register_number=register_number,
            awmf_register_number_full=register_number,
            title=f"Guideline {register_number}",
            publishing_organizations=[OrganizationEntry(name="Org", is_leading=True)],
            download_information=GuidelineDownloadInformation(url="https://example.com/test.pdf", file_path="test.pdf"),
            validity_information=GuidelineValidityInformation(
                version="1.0",
                guideline_creation_date=date(2025, 1, 1),
                valid=True,
                extended_validity=False,
                validity_range=5,
            ),
        )


if __name__ == "__main__":
    unittest.main()
