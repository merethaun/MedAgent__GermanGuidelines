from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import requests
from bson import ObjectId
from pymongo.collection import Collection

from app.constants.mongodb_config import GUIDELINE_PDF_FOLDER
from app.exceptions.knowledge.guideline import GuidelineNotFoundError
from app.models.knowledge.guideline import GuidelineEntry


@dataclass
class GuidelineService:
    """Service for storing and retrieving GuidelineEntry objects in MongoDB."""
    
    guideline_collection: Collection
    
    def create_guideline(self, guideline: GuidelineEntry) -> GuidelineEntry:
        payload = guideline.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)  # allow Mongo to generate ObjectId
        
        result = self.guideline_collection.insert_one(payload)
        return self.get_guideline_by_id(str(result.inserted_id))
    
    def get_guideline_by_id(self, guideline_id: str) -> GuidelineEntry:
        try:
            _id = ObjectId(guideline_id)
        except Exception as e:
            raise GuidelineNotFoundError(f"Invalid guideline_id: {guideline_id}") from e
        
        doc = self.guideline_collection.find_one({"_id": _id})
        if not doc:
            raise GuidelineNotFoundError(f"Guideline not found: {guideline_id}")
        return GuidelineEntry.model_validate(doc)
    
    def list_guidelines(self) -> List[GuidelineEntry]:
        docs = list(self.guideline_collection.find({}))
        return [GuidelineEntry.model_validate(d) for d in docs]
    
    def update_guideline(self, guideline_id: str, guideline: GuidelineEntry) -> GuidelineEntry:
        try:
            _id = ObjectId(guideline_id)
        except Exception as e:
            raise GuidelineNotFoundError(f"Invalid guideline_id: {guideline_id}") from e
        
        payload = guideline.model_dump(by_alias=True, exclude_none=True)
        payload["_id"] = _id  # ensure consistency
        
        res = self.guideline_collection.replace_one({"_id": _id}, payload, upsert=False)
        if res.matched_count == 0:
            raise GuidelineNotFoundError(f"Guideline not found: {guideline_id}")
        return self.get_guideline_by_id(guideline_id)
    
    def delete_guideline(self, guideline_id: str) -> None:
        try:
            _id = ObjectId(guideline_id)
        except Exception as e:
            raise GuidelineNotFoundError(f"Invalid guideline_id: {guideline_id}") from e
        
        res = self.guideline_collection.delete_one({"_id": _id})
        if res.deleted_count == 0:
            raise GuidelineNotFoundError(f"Guideline not found: {guideline_id}")
    
    def download_pdf_to_folder(
            self,
            guideline_id: str,
            url: str,
            filename: Optional[str] = None,
    ) -> GuidelineEntry:
        """Download a PDF from `url` and store it under GUIDELINE_PDF_FOLDER.

        This updates `download_information` in the guideline entry *if that field exists and is mutable*.
        """
        guideline = self.get_guideline_by_id(guideline_id)
        
        target_dir = Path(GUIDELINE_PDF_FOLDER)
        target_dir.mkdir(parents=True, exist_ok=True)
        
        if filename is None:
            filename = f"{guideline.awmf_register_number_full}.pdf"
        
        target_path = target_dir / filename
        
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        target_path.write_bytes(r.content)
        
        now = datetime.now(timezone.utc)
        try:
            guideline.download_information.url = url
            guideline.download_information.download_date = now
            guideline.download_information.file_path = str(target_path)
        except Exception:
            pass
        
        return self.update_guideline(guideline_id, guideline)
