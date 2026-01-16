from typing import List, Union

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.results import InsertOneResult, DeleteResult, UpdateResult

from app.models.system.workflow_system import WorkflowConfig
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class WorkflowSystemStorageService:
    """
    Synchronous service layer to manage CRUD operations for workflow systems,
    keeping both MongoDB and in-memory interaction system in sync.
    """
    
    def __init__(self, system_collection: Collection):
        self.system_collection = system_collection
    
    def create_workflow_entry(self, workflow_config: WorkflowConfig) -> WorkflowConfig:
        """
        Create a new workflow in MongoDB and initialize it in the runtime system.
        """
        logger.debug(f"Creating workflow entry for: {workflow_config.name}")
        
        data = workflow_config.model_dump(by_alias=True, exclude_unset=True)
        result: InsertOneResult = self.system_collection.insert_one(data)
        
        entry = self.get_workflow_entry_by_id(result.inserted_id)
        
        logger.info(f"Workflow entry created with ID: {entry.id}")
        return entry
    
    def get_workflow_entry_by_id(self, wf_id: Union[str, ObjectId]) -> WorkflowConfig:
        """
        Retrieve a workflow config by MongoDB ID (string or ObjectId).
        """
        wf_oid = ObjectId(wf_id) if isinstance(wf_id, str) else wf_id
        entry = self.system_collection.find_one({"_id": wf_oid})
        
        if not entry:
            raise ValueError(f"Workflow entry not found: {wf_oid}")
        
        return WorkflowConfig(**entry)
    
    def get_workflow_entry_by_name(self, name: str) -> WorkflowConfig:
        """
        Retrieve a workflow config by name.
        If multiple workflows with the same name exist, raises a ValueError listing the IDs.
        """
        cursor = self.system_collection.find({"name": name})
        entries = list(cursor)
        
        if not entries:
            raise ValueError(f"Workflow entry not found: {name}")
        elif len(entries) > 1:
            ids = [str(entry["_id"]) for entry in entries]
            raise ValueError(
                f"Multiple workflows found with name '{name}'. Conflicting IDs: {ids}. Please use the ID instead.",
            )
        
        entry = entries[0]
        
        return WorkflowConfig(**entry)
    
    def update_workflow_entry(self, wf_id: Union[str, ObjectId], updated_config: WorkflowConfig) -> WorkflowConfig:
        """
        Update an existing workflow in MongoDB and reinitialize the system entry.
        """
        wf_oid = ObjectId(wf_id) if isinstance(wf_id, str) else wf_id
        logger.info(f"Updating workflow entry with ID: {wf_oid}")
        
        data = updated_config.model_dump(by_alias=True, exclude_unset=True)
        result: UpdateResult = self.system_collection.update_one({"_id": wf_oid}, {"$set": data})
        
        if result.modified_count > 0:
            logger.info(f"Workflow entry updated. Reinitializing workflow ID: {wf_oid}")
        else:
            logger.warning(f"No workflow entry updated for ID: {wf_oid}")
        
        entry = self.get_workflow_entry_by_id(wf_oid)
        logger.info(f"Successfully updated MongoDB entry for workflow ID: {entry.id}")
        
        return entry
    
    def delete_workflow_entry(self, wf_id: Union[str, ObjectId]) -> DeleteResult:
        """
        Delete a workflow from MongoDB and remove it from the system service.
        """
        wf_oid = ObjectId(wf_id) if isinstance(wf_id, str) else wf_id
        logger.info(f"Deleting workflow entry with ID: {wf_oid}")
        
        result: DeleteResult = self.system_collection.delete_one({"_id": wf_oid})
        return result
    
    def list_all_workflows(self) -> List[WorkflowConfig]:
        """
        Return all workflow entries in MongoDB.
        """
        all_systems = list(self.system_collection.find())
        
        return [WorkflowConfig(**sys) for sys in all_systems]
