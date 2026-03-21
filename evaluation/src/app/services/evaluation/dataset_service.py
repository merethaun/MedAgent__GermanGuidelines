import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.collection import Collection

from app.models.evaluation.dataset import BoundingBox, ExpectedRetrievalSnippet, QuestionClassification, QuestionEntry, QuestionGroup
from app.services.backend_api_client import BackendApiClient


@dataclass
class DatasetService:
    question_group_collection: Collection
    question_entry_collection: Collection
    backend_client: BackendApiClient

    def create_question_group(self, group: QuestionGroup) -> QuestionGroup:
        payload = group.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)
        result = self.question_group_collection.insert_one(payload)
        return self.get_question_group(str(result.inserted_id))

    def list_question_groups(self) -> List[QuestionGroup]:
        return [
            QuestionGroup.model_validate(doc)
            for doc in self.question_group_collection.find({}).sort("created_at", -1)
        ]

    def get_question_group(self, group_id: str) -> QuestionGroup:
        doc = self.question_group_collection.find_one({"_id": self._oid(group_id, "question_group_id")})
        if not doc:
            raise ValueError(f"Question group not found: {group_id}")
        return QuestionGroup.model_validate(doc)

    def create_question(self, question: QuestionEntry) -> QuestionEntry:
        self.get_question_group(str(question.question_group_id))
        payload = question.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)
        payload["question_group_id"] = str(question.question_group_id)
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self.question_entry_collection.insert_one(payload)
        return self.get_question(str(result.inserted_id))

    def get_question(self, question_id: str) -> QuestionEntry:
        doc = self.question_entry_collection.find_one({"_id": self._oid(question_id, "question_id")})
        if not doc:
            raise ValueError(f"Question entry not found: {question_id}")
        return QuestionEntry.model_validate(doc)

    def list_questions(
            self,
            *,
            question_group_id: Optional[str] = None,
            question: Optional[str] = None,
            super_class: Optional[str] = None,
            sub_class: Optional[str] = None,
    ) -> List[QuestionEntry]:
        query: Dict[str, object] = {}
        if question_group_id:
            query["question_group_id"] = str(question_group_id)
        if question:
            query["question"] = {"$regex": question, "$options": "i"}
        if super_class:
            query["classification.super_class"] = super_class
        if sub_class:
            query["classification.sub_class"] = sub_class
        return [
            QuestionEntry.model_validate(doc)
            for doc in self.question_entry_collection.find(query).sort("created_at", -1)
        ]

    def update_question(self, question_id: str, question: QuestionEntry) -> QuestionEntry:
        oid = self._oid(question_id, "question_id")
        self.get_question_group(str(question.question_group_id))
        payload = question.model_dump(by_alias=True, exclude_none=True)
        payload["_id"] = oid
        payload["question_group_id"] = str(question.question_group_id)
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self.question_entry_collection.replace_one({"_id": oid}, payload, upsert=False)
        if result.matched_count == 0:
            raise ValueError(f"Question entry not found: {question_id}")
        return self.get_question(question_id)

    def delete_question(self, question_id: str) -> None:
        result = self.question_entry_collection.delete_one({"_id": self._oid(question_id, "question_id")})
        if result.deleted_count == 0:
            raise ValueError(f"Question entry not found: {question_id}")

    def import_questions_from_csv(self, question_group_id: str, csv_bytes: bytes, access_token: str) -> List[QuestionEntry]:
        self.get_question_group(question_group_id)
        decoded = csv_bytes.decode("utf-8-sig", errors="ignore")
        rows = list(csv.DictReader(io.StringIO(decoded)))
        guideline_lookup: Dict[str, Dict[str, Optional[str]]] = {}
        guideline_lookup_loaded = False

        inserted_entries: List[QuestionEntry] = []
        current_key: Optional[tuple] = None
        current_entry: Optional[QuestionEntry] = None

        for row in rows:
            question_text = (row.get("Question") or "").strip()
            super_class = (row.get("Question supercategory") or "").strip()
            sub_class = (row.get("Question subcategory") or "").strip()
            correct_answer = (row.get("Correct Answer") or "").strip() or None
            note = (row.get("Comment") or "").strip() or None
            key = (question_text, super_class, sub_class, correct_answer or "", note or "")

            if not question_text or not super_class or not sub_class:
                continue

            if current_key != key:
                if current_entry is not None:
                    inserted_entries.append(self.create_question(current_entry))
                current_key = key
                current_entry = QuestionEntry(
                    question_group_id=ObjectId(question_group_id),
                    question=question_text,
                    classification=QuestionClassification(super_class=super_class, sub_class=sub_class),
                    correct_answer=correct_answer,
                    note=note,
                    expected_retrieval=[],
                )

            assert current_entry is not None
            if not guideline_lookup_loaded and self._row_needs_guideline_lookup(row):
                try:
                    guideline_lookup = self._build_guideline_lookup(access_token)
                except Exception as exc:
                    raise ValueError(
                        "CSV import needs backend guideline resolution for legacy columns. "
                        "Use 'Answer Guideline Source' and 'Answer Bounding Boxes', or configure "
                        "the evaluation user with backend guideline access in Keycloak.",
                    ) from exc
                guideline_lookup_loaded = True
            snippet = self._snippet_from_row(row, guideline_lookup, access_token)
            if snippet is not None:
                current_entry.expected_retrieval.append(snippet)

        if current_entry is not None:
            inserted_entries.append(self.create_question(current_entry))

        return inserted_entries

    def export_questions_to_csv(self, question_group_id: Optional[str] = None) -> str:
        entries = self.list_questions(question_group_id=question_group_id)
        output = io.StringIO()
        fieldnames = [
            "Question ID",
            "Question group",
            "Question supercategory",
            "Question subcategory",
            "Question",
            "Correct Answer",
            "Answer Guideline Source",
            "Answer Guideline Title",
            "Answer Bounding Boxes",
            "Answer Reference Type",
            "Retrieval Text",
            "Comment",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        group_names = {str(group.id): group.name for group in self.list_question_groups()}
        for entry in entries:
            base_row = {
                "Question ID": str(entry.id) if entry.id else "",
                "Question group": group_names.get(str(entry.question_group_id), ""),
                "Question supercategory": entry.classification.super_class,
                "Question subcategory": entry.classification.sub_class,
                "Question": entry.question,
                "Correct Answer": entry.correct_answer or "",
                "Comment": entry.note or "",
            }
            if not entry.expected_retrieval:
                writer.writerow({**base_row, "Retrieval Text": ""})
                continue
            for snippet in entry.expected_retrieval:
                writer.writerow(
                    {
                        **base_row,
                        "Answer Guideline Source": snippet.guideline_source or "",
                        "Answer Guideline Title": snippet.guideline_title or "",
                        "Answer Bounding Boxes": json.dumps(
                            [bbox.model_dump() for bbox in snippet.bounding_boxes],
                            ensure_ascii=False,
                        ) if snippet.bounding_boxes else "",
                        "Answer Reference Type": snippet.reference_type.value if snippet.reference_type else "",
                        "Retrieval Text": snippet.retrieval_text or "",
                    },
                )
        return output.getvalue()

    @staticmethod
    def _row_needs_guideline_lookup(row: Dict[str, str]) -> bool:
        guideline_source = (row.get("Answer Guideline Source") or "").strip()
        legacy_guideline = (row.get("Answer Guideline") or "").strip()
        bounding_boxes_raw = (row.get("Answer Bounding Boxes") or row.get("Bounding Boxes") or "").strip()
        page_hint = (row.get("Answer Gpage") or "").strip()
        retrieval_text = (row.get("Retrieval Text") or "").strip()

        if legacy_guideline and not guideline_source:
            if not legacy_guideline.startswith("http://") and not legacy_guideline.startswith("https://"):
                return True

        if page_hint and not bounding_boxes_raw and retrieval_text and (guideline_source or legacy_guideline):
            return True

        return False

    def _build_guideline_lookup(self, access_token: str) -> Dict[str, Dict[str, Optional[str]]]:
        guidelines = self.backend_client.list_guidelines(access_token)
        lookup: Dict[str, Dict[str, Optional[str]]] = {}
        for guideline in guidelines:
            awmf_full = (guideline.get("awmf_register_number_full") or "").strip()
            title = (guideline.get("title") or "").strip()
            download_info = guideline.get("download_information") or {}
            source_url = (download_info.get("url") or "").strip()
            payload = {
                "guideline_id": str(guideline.get("_id") or ""),
                "guideline_title": title or None,
                "guideline_source": source_url or None,
            }
            if awmf_full:
                lookup[awmf_full] = payload
            if source_url:
                lookup[source_url] = payload
        return lookup

    def _snippet_from_row(
            self,
            row: Dict[str, str],
            guideline_lookup: Dict[str, Dict[str, Optional[str]]],
            access_token: str,
    ) -> Optional[ExpectedRetrievalSnippet]:
        guideline_source = (row.get("Answer Guideline Source") or "").strip() or None
        legacy_guideline = (row.get("Answer Guideline") or "").strip() or None
        retrieval_text = (row.get("Retrieval Text") or "").strip()
        reference_type = (row.get("Answer Reference Type") or "").strip() or None
        guideline_title = (row.get("Answer Guideline Title") or "").strip() or None
        bounding_boxes_raw = (row.get("Answer Bounding Boxes") or row.get("Bounding Boxes") or "").strip()
        guideline_metadata = guideline_lookup.get(guideline_source or legacy_guideline or "", {})

        if not guideline_source and legacy_guideline:
            if legacy_guideline.startswith("http://") or legacy_guideline.startswith("https://"):
                guideline_source = legacy_guideline
            else:
                guideline_source = guideline_metadata.get("guideline_source")

        if not guideline_title:
            guideline_title = guideline_metadata.get("guideline_title")

        bounding_boxes = self._parse_bounding_boxes(bounding_boxes_raw)
        if not bounding_boxes and retrieval_text:
            bounding_boxes = self._resolve_legacy_bounding_boxes(
                row.get("Answer Gpage"),
                retrieval_text,
                guideline_metadata,
                access_token,
            )

        if not any([guideline_source, retrieval_text, bounding_boxes, guideline_title, reference_type]):
            return None

        return ExpectedRetrievalSnippet(
            guideline_source=guideline_source,
            guideline_title=guideline_title,
            bounding_boxes=bounding_boxes,
            reference_type=reference_type,
            retrieval_text=retrieval_text,
        )

    @staticmethod
    def _parse_bounding_boxes(raw: str) -> List[BoundingBox]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Answer Bounding Boxes must be valid JSON") from exc

        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError("Answer Bounding Boxes must be a JSON object or array")

        return [BoundingBox.model_validate(item) for item in parsed]

    def _resolve_legacy_bounding_boxes(
            self,
            page_raw: Optional[str],
            retrieval_text: str,
            guideline_metadata: Dict[str, Optional[str]],
            access_token: str,
    ) -> List[BoundingBox]:
        guideline_id = guideline_metadata.get("guideline_id")
        if not guideline_id:
            return []

        page_hint = self._parse_page_hint(page_raw)
        try:
            payload = self.backend_client.find_bounding_boxes(
                access_token=access_token,
                guideline_id=guideline_id,
                text=retrieval_text,
                start_page=page_hint,
                end_page=page_hint,
            ) or []
        except Exception:
            return []

        return [BoundingBox.model_validate(item) for item in payload]

    @staticmethod
    def _parse_page_hint(page_raw: Optional[str]) -> Optional[int]:
        raw = (page_raw or "").strip()
        if not raw:
            return None
        try:
            return int(float(raw))
        except ValueError:
            return None

    @staticmethod
    def _oid(raw_id: str, label: str) -> ObjectId:
        try:
            return ObjectId(raw_id)
        except Exception as exc:
            raise ValueError(f"Invalid {label}: {raw_id}") from exc
