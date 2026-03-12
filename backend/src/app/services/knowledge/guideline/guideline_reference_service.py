from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from bson import ObjectId
from pymongo.collection import Collection

from app.exceptions.knowledge.guideline import GuidelineNotFoundError, GuidelineReferenceGroupNotFoundError, GuidelineReferenceNotFoundError
from app.models.knowledge.guideline import (
    GuidelineReference,
    GuidelineReferenceGroup,
    REFERENCE_TYPE_MAP,
    ReferenceType,
)


@dataclass
class GuidelineReferenceService:
    """Service for storing and retrieving guideline references and reference groups in MongoDB."""
    
    guideline_collection: Collection
    reference_groups_collection: Collection
    reference_collection: Collection
    
    # -------------------------
    # Helpers
    # -------------------------
    @staticmethod
    def _oid(value: Union[str, ObjectId], *, what: str = "id") -> ObjectId:
        """Convert a string/ObjectId into ObjectId, raise a domain error on invalid input."""
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(value)
        except Exception as e:
            raise GuidelineNotFoundError(f"Invalid {what}: {value}") from e
    
    @staticmethod
    def _deserialize_reference(doc: Dict) -> GuidelineReference:
        """Deserialize a polymorphic reference document using REFERENCE_TYPE_MAP."""
        reference_type = doc.get("type")
        model_cls: Optional[Type[GuidelineReference]] = REFERENCE_TYPE_MAP.get(reference_type)
        if not model_cls:
            # keep this as a hard error (same behavior as your get_reference_by_id)
            raise ValueError(f"Unknown reference type: {reference_type}")
        return model_cls.model_validate(doc)

    def _resolve_guideline_id(self, value: Union[str, ObjectId]) -> ObjectId:
        """Resolve a guideline reference by ObjectId or stable string fields."""
        if isinstance(value, ObjectId):
            if not self.guideline_collection.find_one({"_id": value}, {"_id": 1}):
                raise GuidelineNotFoundError(f"Guideline not found: {value}")
            return value

        if ObjectId.is_valid(value):
            guideline_id = ObjectId(value)
            if not self.guideline_collection.find_one({"_id": guideline_id}, {"_id": 1}):
                raise GuidelineNotFoundError(f"Guideline not found: {value}")
            return guideline_id

        doc = self.guideline_collection.find_one(
            {
                "$or": [
                    {"title": value},
                    {"awmf_register_number": value},
                    {"awmf_register_number_full": value},
                ],
            },
            {"_id": 1},
            sort=[("_id", -1)],
        )
        if not doc:
            raise GuidelineNotFoundError(f"Guideline not found: {value}")
        return doc["_id"]

    def _resolve_reference_group_id(self, value: Union[str, ObjectId]) -> ObjectId:
        """Resolve a reference group by ObjectId or by group name."""
        if isinstance(value, ObjectId):
            if not self.reference_groups_collection.find_one({"_id": value}, {"_id": 1}):
                raise GuidelineReferenceGroupNotFoundError(f"Reference group not found: {value}")
            return value

        if ObjectId.is_valid(value):
            group_id = ObjectId(value)
            if not self.reference_groups_collection.find_one({"_id": group_id}, {"_id": 1}):
                raise GuidelineReferenceGroupNotFoundError(f"Reference group not found: {value}")
            return group_id

        doc = self.reference_groups_collection.find_one(
            {"name": value},
            {"_id": 1},
            sort=[("_id", -1)],
        )
        if not doc:
            raise GuidelineReferenceGroupNotFoundError(f"Reference group not found: {value}")
        return doc["_id"]

    def _normalize_reference_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve string identifiers to Mongo ObjectIds before validation/persistence."""
        normalized = dict(payload)

        if "guideline_id" in normalized and normalized["guideline_id"] is not None:
            normalized["guideline_id"] = self._resolve_guideline_id(normalized["guideline_id"])

        if "reference_group_id" in normalized and normalized["reference_group_id"] is not None:
            normalized["reference_group_id"] = self._resolve_reference_group_id(normalized["reference_group_id"])

        normalized.pop("_id", None)
        return normalized

    @staticmethod
    def _prepare_reference_for_mongo(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure Mongo-bound reference payloads keep foreign keys as real ObjectIds."""
        mongo_payload = dict(payload)

        if "guideline_id" in mongo_payload and mongo_payload["guideline_id"] is not None:
            mongo_payload["guideline_id"] = ObjectId(mongo_payload["guideline_id"])

        if "reference_group_id" in mongo_payload and mongo_payload["reference_group_id"] is not None:
            mongo_payload["reference_group_id"] = ObjectId(mongo_payload["reference_group_id"])

        mongo_payload.pop("_id", None)
        return mongo_payload
    
    # -------------------------
    # Reference groups (CRUD)
    # -------------------------
    def create_reference_group(self, reference_group: GuidelineReferenceGroup) -> GuidelineReferenceGroup:
        payload = reference_group.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)
        
        res = self.reference_groups_collection.insert_one(payload)
        return self.get_reference_group_by_id(str(res.inserted_id))
    
    def get_reference_group_by_id(self, reference_group_id: Union[str, ObjectId]) -> GuidelineReferenceGroup:
        _id = self._oid(reference_group_id, what="reference_group_id")
        doc = self.reference_groups_collection.find_one({"_id": _id})
        if not doc:
            raise GuidelineReferenceGroupNotFoundError(f"Reference group not found: {reference_group_id}")
        return GuidelineReferenceGroup.model_validate(doc)
    
    def get_reference_group_by_name(self, name: str) -> GuidelineReferenceGroup:
        doc = self.reference_groups_collection.find_one({"name": name})
        if not doc:
            raise GuidelineReferenceGroupNotFoundError(f"Reference group not found: {name}")
        return GuidelineReferenceGroup.model_validate(doc)
    
    def list_reference_groups(self) -> List[GuidelineReferenceGroup]:
        docs = list(self.reference_groups_collection.find({}))
        return [GuidelineReferenceGroup.model_validate(d) for d in docs]
    
    def update_reference_group(
            self,
            reference_group_id: Union[str, ObjectId],
            update_data: Union[GuidelineReferenceGroup, Dict],
    ) -> GuidelineReferenceGroup:
        _id = self._oid(reference_group_id, what="reference_group_id")
        
        # noinspection DuplicatedCode
        if isinstance(update_data, GuidelineReferenceGroup):
            update_fields = update_data.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)
        else:
            update_fields = dict(update_data)
        
        # prevent accidental id overwrite
        update_fields.pop("_id", None)
        
        res = self.reference_groups_collection.update_one({"_id": _id}, {"$set": update_fields})
        if res.matched_count == 0:
            raise GuidelineReferenceGroupNotFoundError(f"Reference group not found: {reference_group_id}")
        
        return self.get_reference_group_by_id(_id)
    
    def delete_reference_group_by_id(self, reference_group_id: Union[str, ObjectId]) -> None:
        _id = self._oid(reference_group_id, what="reference_group_id")
        res = self.reference_groups_collection.delete_one({"_id": _id})
        if res.deleted_count == 0:
            raise GuidelineReferenceGroupNotFoundError(f"Reference group not found: {reference_group_id}")
    
    # -------------------------
    # References (CRUD)
    # -------------------------
    def create_reference(self, reference: Union[GuidelineReference, Dict[str, Any]]) -> GuidelineReference:
        if isinstance(reference, dict):
            payload = dict(reference)
        else:
            payload = reference.model_dump(by_alias=True, exclude_none=True)

        payload = self._normalize_reference_payload(payload)
        reference_model = self._deserialize_reference(payload)
        payload = self._prepare_reference_for_mongo(
            reference_model.model_dump(by_alias=True, exclude_none=True),
        )
        payload["created_date"] = datetime.now(timezone.utc)
        
        res = self.reference_collection.insert_one(payload)
        return self.get_reference_by_id(str(res.inserted_id))
    
    def get_reference_by_id(self, reference_id: Union[str, ObjectId]) -> GuidelineReference:
        _id = self._oid(reference_id, what="reference_id")
        doc = self.reference_collection.find_one({"_id": _id})
        if not doc:
            raise GuidelineReferenceNotFoundError(f"Reference not found: {reference_id}")
        return self._deserialize_reference(doc)
    
    def list_references(
            self,
            reference_group_id: Optional[Union[str, ObjectId]] = None,
            guideline_id: Optional[Union[str, ObjectId]] = None,
            reference_type: Optional[ReferenceType] = None,
    ) -> List[GuidelineReference]:
        query: Dict = {}
        
        if reference_group_id is not None:
            query["reference_group_id"] = self._resolve_reference_group_id(reference_group_id)
        
        if guideline_id is not None:
            query["guideline_id"] = self._resolve_guideline_id(guideline_id)
        
        if reference_type is not None:
            query["type"] = reference_type.value
        
        docs = list(self.reference_collection.find(query))
        
        # mirror your old behavior: skip unknown types during "list", but keep "get by id" strict
        results: List[GuidelineReference] = []
        for doc in docs:
            try:
                results.append(self._deserialize_reference(doc))
            except ValueError:
                # unknown type -> ignore in list (same as previous implementation)
                continue
        
        return results
    
    def update_reference(
            self,
            reference_id: Union[str, ObjectId],
            update_data: Union[GuidelineReference, Dict],
    ) -> GuidelineReference:
        _id = self._oid(reference_id, what="reference_id")
        
        # noinspection DuplicatedCode
        if isinstance(update_data, GuidelineReference):
            update_fields = update_data.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)
        else:
            update_fields = dict(update_data)
        
        update_fields = self._normalize_reference_payload(update_fields)
        update_fields = self._prepare_reference_for_mongo(update_fields)
        
        res = self.reference_collection.update_one({"_id": _id}, {"$set": update_fields})
        if res.matched_count == 0:
            raise GuidelineReferenceNotFoundError(f"Reference not found: {reference_id}")
        
        return self.get_reference_by_id(_id)
    
    def delete_reference_by_id(self, reference_id: Union[str, ObjectId]) -> None:
        _id = self._oid(reference_id, what="reference_id")
        res = self.reference_collection.delete_one({"_id": _id})
        if res.deleted_count == 0:
            raise GuidelineReferenceNotFoundError(f"Reference not found: {reference_id}")
    
    def delete_references_by_guideline_id(self, guideline_id: Union[str, ObjectId]) -> Tuple[int, List[str]]:
        gid = self._resolve_guideline_id(guideline_id)
        
        refs = list(self.reference_collection.find({"guideline_id": gid}, {"_id": 1}))
        if not refs:
            return 0, []
        
        reference_ids = [str(d["_id"]) for d in refs]
        res = self.reference_collection.delete_many({"guideline_id": gid})
        return res.deleted_count, reference_ids
    
    def delete_references_by_reference_group_id(
            self,
            reference_group_id: Union[str, ObjectId],
    ) -> Tuple[int, List[str]]:
        rgid = self._resolve_reference_group_id(reference_group_id)
        
        refs = list(self.reference_collection.find({"reference_group_id": rgid}, {"_id": 1}))
        if not refs:
            return 0, []
        
        reference_ids = [str(d["_id"]) for d in refs]
        res = self.reference_collection.delete_many({"reference_group_id": rgid})
        return res.deleted_count, reference_ids
