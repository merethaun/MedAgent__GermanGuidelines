from datetime import datetime, timezone
from typing import Union, List, Tuple, Optional, Dict

from bson import ObjectId
from pymongo.collection import Collection

from app.models.knowledge.guidelines import (
    GuidelineReference,
    REFERENCE_TYPE_MAP,
    ReferenceType,
    GuidelineReferenceGroup,
)
from app.utils.knowledge.mongodb_object_id import as_object_id
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class GuidelineReferenceService:
    """
    Service layer to manage CRUD operations for guideline references.
    """
    
    def __init__(self, reference_groups_collection: Collection, reference_collection: Collection):
        self.reference_groups_collection = reference_groups_collection
        self.collection = reference_collection
    
    def create_reference_group(self, reference_group: GuidelineReferenceGroup) -> GuidelineReferenceGroup:
        logger.debug(f"Creating reference group with name: {reference_group.name}")
        data = reference_group.model_dump(by_alias=True, exclude_unset=True)
        result = self.reference_groups_collection.insert_one(data)
        logger.info(f"Reference group created with ID: {result.inserted_id}")
        return self.get_reference_group_by_id(result.inserted_id)
    
    def get_reference_group_by_id(self, reference_group_id: Union[str, ObjectId]) -> GuidelineReferenceGroup:
        logger.debug(f"Fetching reference group by ID: {reference_group_id}")
        obj_id = ObjectId(reference_group_id) if isinstance(reference_group_id, str) else reference_group_id
        doc = self.reference_groups_collection.find_one({"_id": obj_id})
        if not doc:
            logger.warning(f"Reference group with ID {reference_group_id} not found.")
            raise ValueError(f"Reference group not found: {reference_group_id}")
        return GuidelineReferenceGroup(**doc)
    
    def get_reference_group_by_name(self, name: str) -> GuidelineReferenceGroup:
        logger.debug(f"Fetching reference group by name: {name}")
        doc = self.reference_groups_collection.find_one({"name": name})
        if not doc:
            logger.warning(f"Reference group with name {name} not found.")
            raise ValueError(f"Reference group not found: {name}")
        return GuidelineReferenceGroup(**doc)
    
    def get_all_reference_groups(self) -> List[GuidelineReferenceGroup]:
        logger.info("Fetching all guideline reference groups (id + name)")
        references = list(self.reference_groups_collection.find())
        
        if len(references) == 0:
            logger.warning("No reference groups found.")
        else:
            logger.info(f"Successfully fetched {len(references)} reference groups.")
        
        results = []
        for doc in references:
            try:
                results.append(GuidelineReferenceGroup(**doc))
            except Exception as e:
                logger.warning(f"Failed to deserialize reference with ID {doc.get('_id')}: {str(e)}")
        
        return results
    
    def update_reference_group(
            self, reference_group_id: Union[str, ObjectId], update_data: GuidelineReferenceGroup,
    ) -> GuidelineReferenceGroup:
        """
        Update an existing guideline reference group by its ID.

        Args:
            reference_group_id: The ID of the reference group to update.
            update_data: Partial or complete updated data for the reference group.

        Returns:
            Updated GuidelineReferenceGroup instance.

        Raises:
            ValueError: If the reference group is not found or the update fails.
        """
        logger.debug(f"Updating reference group with ID: {reference_group_id}")
        obj_id = ObjectId(reference_group_id) if isinstance(reference_group_id, str) else reference_group_id
        
        # Build update object from the supplied data (exclude unset fields for partial updates)
        update_fields = update_data.model_dump(exclude_unset=True)
        
        # Attempt the update
        result = self.reference_groups_collection.update_one(
            {"_id": obj_id},
            {"$set": update_fields},
        )
        if result.matched_count == 0:
            logger.warning(f"Reference group with ID {reference_group_id} not found.")
            raise ValueError(f"Reference group not found: {reference_group_id}")
        if result.modified_count == 0:
            logger.warning(f"No changes made to the reference group with ID {reference_group_id}.")
            raise ValueError(f"No changes made to the reference group: {reference_group_id}")
        
        # Return the updated object
        logger.info(f"Successfully updated reference group with ID: {reference_group_id}")
        return self.get_reference_group_by_id(obj_id)
    
    def delete_reference_group_by_id(self, reference_group_id: Union[str, ObjectId]) -> bool:
        obj_id = ObjectId(reference_group_id) if isinstance(reference_group_id, str) else reference_group_id
        
        if not self.reference_groups_collection.find_one({"_id": obj_id}):
            logger.warning(f"Reference group with ID {reference_group_id} not found.")
            raise ValueError(f"Reference group not found: {reference_group_id}")
        
        result = self.reference_groups_collection.delete_one({"_id": obj_id})
        
        if result.deleted_count > 0:
            logger.info(f"Successfully deleted reference group with ID: {reference_group_id}")
            return True
        else:
            logger.warning(f"Failed to delete reference group with ID: {reference_group_id}")
            return False
    
    def create_reference(self, reference: GuidelineReference) -> GuidelineReference:
        """
        Insert a new reference into the database.

        Args:
            reference: Pydantic model of type GuidelineReference (e.g., GuidelineTextReference).

        Returns:
            The inserted reference as a Pydantic model instance.
        """
        logger.debug(f"Creating reference of type: {reference.type}")
        data = reference.model_dump(by_alias=True, exclude_unset=True)
        if data.get('_id') is None:
            data.pop('_id', None)
        data["created_date"] = datetime.now(timezone.utc)
        result = self.collection.insert_one(data)
        logger.info(f"Reference created with ID: {result.inserted_id}")
        # TODO: check whether valid -> can find in guideline?
        return self.get_reference_by_id(result.inserted_id)
    
    def get_reference_by_id(self, reference_id: Union[str, ObjectId]) -> GuidelineReference:
        """
        Fetch and deserialize a reference from the database.

        Args:
            reference_id: ObjectId or string

        Returns:
            Deserialized GuidelineReference instance
        """
        logger.debug(f"Fetching reference by ID: {reference_id}")
        obj_id = ObjectId(reference_id) if isinstance(reference_id, str) else reference_id
        doc = self.collection.find_one({"_id": obj_id})
        if not doc:
            logger.warning(f"Reference with ID {reference_id} not found.")
            raise ValueError(f"Reference not found: {reference_id}")
        
        reference_type = doc.get("type")
        model_cls = REFERENCE_TYPE_MAP.get(reference_type)
        if not model_cls:
            logger.error(f"Unknown reference type '{reference_type}' in document")
            raise ValueError(f"Unknown reference type: {reference_type}")
        
        return model_cls(**doc)
    
    def get_all_references(
            self,
            reference_group_id: Optional[Union[str, ObjectId]] = None,
            guideline_id: Optional[Union[str, ObjectId]] = None,
            reference_type: Optional[ReferenceType] = None,
    ) -> List[GuidelineReference]:
        """
        Fetch all references, optionally filtered by guideline ID and reference type.
    
        Args:
            reference_group_id: Optional reference group ID to filter references
            guideline_id: Optional guideline ID to filter references
            reference_type: Optional reference type to filter references
        
        Returns:
            List of deserialized GuidelineReference instances
    
        Raises:
            ValueError: If guideline_id is provided but in an invalid format
        """
        logger.info("Starting reference search with filters")
        logger.debug("Building reference query with provided filters.")
        
        query = {}
        
        # Apply reference_group_id filter if provided
        if reference_group_id:
            try:
                obj_id = as_object_id(reference_group_id)
                query["reference_group_id"] = obj_id
                logger.debug(f"Filter applied: reference_group_id = {reference_group_id}")
            except Exception as e:
                logger.warning(f"Invalid reference_group_id format: {reference_group_id}. Error: {str(e)}")
                raise ValueError(f"Invalid reference_group_id format: {reference_group_id}")
        
        # Apply guideline_id filter if provided
        if guideline_id:
            try:
                obj_id = as_object_id(guideline_id)
                query["guideline_id"] = obj_id
                logger.debug(f"Filter applied: guideline_id = {guideline_id}")
            except Exception as e:
                logger.warning(f"Invalid guideline_id format: {guideline_id}. Error: {str(e)}")
                raise ValueError(f"Invalid guideline_id format: {guideline_id}")
        
        # Apply reference_type filter if provided
        if reference_type:
            query["type"] = reference_type.value
            logger.debug(f"Filter applied: reference_type = {reference_type.value}")
        
        logger.info(f"Executing reference query: {query}")
        references = list(self.collection.find(query))
        
        if len(references) == 0:
            logger.warning("No references found matching query.")
        else:
            logger.info(f"Successfully fetched {len(references)} references matching query.")
        
        # Deserialize the references
        results = []
        for doc in references:
            reference_type = doc.get("type")
            model_cls = REFERENCE_TYPE_MAP.get(reference_type)
            if not model_cls:
                logger.warning(f"Unknown reference type '{reference_type}' in document with ID {doc.get('_id')}")
                continue
            try:
                reference = model_cls(**doc)
                results.append(reference)
            except Exception as e:
                logger.warning(f"Failed to deserialize reference with ID {doc.get('_id')}: {str(e)}")
        
        return results
    
    def delete_reference_by_id(self, reference_id: Union[str, ObjectId]) -> bool:
        """
        Delete a reference by its ID.

        Args:
            reference_id: ObjectId or string ID of the reference to delete

        Returns:
            True if deletion was successful, False if reference was not found
            
        Raises:
            ValueError: If reference was not found
        """
        logger.debug(f"Attempting to delete reference with ID: {reference_id}")
        obj_id = ObjectId(reference_id) if isinstance(reference_id, str) else reference_id
        
        # Check if reference exists
        if not self.collection.find_one({"_id": obj_id}):
            logger.warning(f"Reference with ID {reference_id} not found.")
            raise ValueError(f"Reference not found: {reference_id}")
        
        result = self.collection.delete_one({"_id": obj_id})
        
        if result.deleted_count > 0:
            logger.info(f"Successfully deleted reference with ID: {reference_id}")
            return True
        else:
            logger.warning(f"Failed to delete reference with ID: {reference_id}")
            return False
    
    def delete_references_by_guideline_id(self, guideline_id: Union[str, ObjectId]) -> Tuple[int, List[str]]:
        """
        Delete all references associated with a specific guideline.

        Args:
            guideline_id: ObjectId or string ID of the guideline

        Returns:
            Tuple containing (number of deleted references, list of reference IDs that were deleted)
        """
        obj_id = ObjectId(guideline_id) if isinstance(guideline_id, str) else guideline_id
        logger.debug(f"Deleting references for guideline {obj_id}")
        
        try:
            references = list(self.collection.find({"guideline_id": obj_id}))
            if not references:
                logger.info(f"No references found for guideline {obj_id}")
                return 0, []
            
            reference_ids = [str(doc["_id"]) for doc in references]
            result = self.collection.delete_many({"guideline_id": obj_id})
            logger.info(f"Deleted {result.deleted_count} references for guideline {obj_id}")
            return result.deleted_count, reference_ids
        
        except Exception as e:
            logger.error(f"Error deleting references for guideline {obj_id}: {str(e)}")
            raise
    
    def delete_references_by_reference_group_id(
            self, reference_group_id: Union[str, ObjectId],
    ) -> Tuple[int, List[str]]:
        obj_id = ObjectId(reference_group_id) if isinstance(reference_group_id, str) else reference_group_id
        logger.debug(f"Deleting references for guideline group {obj_id}")
        
        try:
            references = list(self.collection.find({"reference_group_id": obj_id}))
            if not references:
                logger.info(f"No references found for guideline group {obj_id}")
                return 0, []
            
            reference_ids = [str(doc["_id"]) for doc in references]
            result = self.collection.delete_many({"reference_group_id": obj_id})
            logger.info(f"Deleted {result.deleted_count} references for guideline group {obj_id}")
            return result.deleted_count, reference_ids
        
        except Exception as e:
            logger.error(f"Error deleting references for guideline group {obj_id}: {str(e)}")
            raise
    
    def update_reference(
            self, reference_id: Union[str, ObjectId], update_data: Union[GuidelineReference, Dict],
    ) -> GuidelineReference:
        """
        Update an existing guideline reference by its ID.

        Args:
            reference_id: The ID of the reference to update.
            update_data: Partial or complete updated data for the reference.

        Returns:
            Updated GuidelineReference instance.

        Raises:
            ValueError: If the reference is not found or the update fails.
        """
        logger.debug(f"Updating reference with ID: {reference_id}")
        obj_id = ObjectId(reference_id) if isinstance(reference_id, str) else reference_id
        
        # Build update object from the supplied data (exclude unset fields for partial updates)
        if isinstance(update_data, GuidelineReference):
            update_fields = update_data.model_dump(exclude_unset=True)
        else:
            update_fields = update_data
        
        # Attempt the update
        result = self.collection.update_one(
            {"_id": obj_id},
            {"$set": update_fields},
        )
        if result.matched_count == 0:
            logger.warning(f"Reference with ID {reference_id} not found.")
            raise ValueError(f"Reference not found: {reference_id}")
        
        # Return the updated object
        logger.info(f"Successfully updated reference with ID: {reference_id}")
        return self.get_reference_by_id(obj_id)
