from dataclasses import dataclass
from typing import List

from bson import ObjectId
from pymongo.collection import Collection

from app.models.system.workflow_system import WorkflowConfig
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class WorkflowSystemStorageService:
    """Persist and retrieve WorkflowConfig documents in MongoDB."""
    
    workflow_collection: Collection
    
    # -------------------------
    # CRUD
    # -------------------------
    def create_workflow(self, workflow: WorkflowConfig) -> WorkflowConfig:
        payload = workflow.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)  # allow Mongo to generate ObjectId
        
        res = self.workflow_collection.insert_one(payload)
        logger.info("Created workflow: id=%s name=%s", str(res.inserted_id), workflow.name)
        return self.get_workflow_by_id(str(res.inserted_id))
    
    def get_workflow_by_id(self, workflow_id: str) -> WorkflowConfig:
        _id = self._oid(workflow_id)
        doc = self.workflow_collection.find_one({"_id": _id})
        if not doc:
            raise ValueError(f"Workflow not found: {workflow_id}")
        return WorkflowConfig.model_validate(doc)
    
    def get_workflow_by_name(self, name: str) -> WorkflowConfig:
        docs = list(self.workflow_collection.find({"name": name}))
        if not docs:
            raise ValueError(f"Workflow not found: name={name}")
        if len(docs) > 1:
            ids = [str(d["_id"]) for d in docs]
            raise ValueError(f"Multiple workflows found for name='{name}': {ids}")
        return WorkflowConfig.model_validate(docs[0])
    
    def list_workflows(self) -> List[WorkflowConfig]:
        docs = list(self.workflow_collection.find({}))
        return [WorkflowConfig.model_validate(d) for d in docs]
    
    def update_workflow(self, workflow_id: str, workflow: WorkflowConfig) -> WorkflowConfig:
        """
        Replace the workflow document completely (recommended for graph-like configs).
        """
        _id = self._oid(workflow_id)
        
        payload = workflow.model_dump(by_alias=True, exclude_none=True)
        payload["_id"] = _id  # enforce consistency
        
        res = self.workflow_collection.replace_one({"_id": _id}, payload, upsert=False)
        if res.matched_count == 0:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        logger.info("Updated workflow: id=%s name=%s", workflow_id, workflow.name)
        return self.get_workflow_by_id(workflow_id)
    
    def delete_workflow(self, workflow_id: str) -> None:
        _id = self._oid(workflow_id)
        res = self.workflow_collection.delete_one({"_id": _id})
        if res.deleted_count == 0:
            raise ValueError(f"Workflow not found: {workflow_id}")
        logger.info("Deleted workflow: id=%s", workflow_id)
    
    # -------------------------
    # Internal
    # -------------------------
    @staticmethod
    def _oid(workflow_id: str) -> ObjectId:
        try:
            return ObjectId(workflow_id)
        except Exception as e:
            raise ValueError(f"Invalid workflow_id: {workflow_id}") from e
