import re
from typing import Union, List, Optional

from bson import ObjectId
from pymongo.collection import Collection

from app.models.guideline_evaluation.question_dataset.question_entry import QuestionEntry, QuestionGroup
from app.services.knowledge.guidelines.references import GuidelineReferenceService
from app.utils.knowledge.mongodb_object_id import as_object_id
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class QuestionDatasetService:
    """
    Service layer to manage CRUD operations for dataset (question-answer).
    """
    
    def __init__(self, dataset_collection: Collection, question_group_collection: Collection, reference_service: GuidelineReferenceService):
        self.dataset_collection = dataset_collection
        self.question_group_collection = question_group_collection
        self.reference_service = reference_service
    
    @staticmethod
    def get_available_super_question_classes():
        return ["Simple", "Complex", "Negative"]
    
    @staticmethod
    def get_available_sub_question_classes(super_question_class):
        if super_question_class == "Simple":
            return ["Text", "Table", "Figure", "Recommendation"]
        elif super_question_class == "Complex":
            return ["Synonym", "Multiple sections", "Multiple guidelines", "Substeps"]
        elif super_question_class == "Negative":
            return [
                "Outside medicine", "Outside OMS", "Outside guidelines", "Patient-specific", "Broken input",
                "False assumption",
            ]
        else:
            msg = f"Unknown super question class: {super_question_class}"
            logger.warning(msg)
            raise ValueError(msg)
    
    def validate_question_classes(self, super_question_class, sub_question_class):
        if super_question_class not in self.get_available_super_question_classes():
            msg = f"Invalid super question class: '{super_question_class}'"
            logger.error(msg)
            raise ValueError(msg)
        if sub_question_class not in self.get_available_sub_question_classes(super_question_class):
            msg = f"Invalid sub question class: {sub_question_class}"
            logger.error(msg)
            raise ValueError(msg)
    
    def create_dataset_entry(self, question_entry: QuestionEntry):
        logger.debug(
            f"Creating {question_entry.classification.super_class} question entry in dataset for question: {question_entry.question}",
        )
        
        self.validate_question_classes(
            question_entry.classification.super_class, question_entry.classification.sub_class,
        )
        
        data = question_entry.model_dump(by_alias=True, exclude_unset=True)
        result = self.dataset_collection.insert_one(data)
        
        logger.info(f"Question entry created with ID: {result.inserted_id}")
        return self.get_question_entry_by_id(result.inserted_id)
    
    def get_question_entry_by_id(self, question_entry_id: Union[str, ObjectId]) -> QuestionEntry:
        logger.debug(f"Fetching question entry by ID: {question_entry_id}")
        obj_id = ObjectId(question_entry_id) if isinstance(question_entry_id, str) else question_entry_id
        doc = self.dataset_collection.find_one({"_id": obj_id})
        if not doc:
            logger.warning(f"Question entry with ID {question_entry_id} not found.")
            raise ValueError(f"Question entry not found: {question_entry_id}")
        return QuestionEntry(**doc)
    
    def get_question_entries(
            self, question: Optional[str], super_class: Optional[str] = None, sub_class: Optional[str] = None,
            guideline_id: Optional[Union[str, ObjectId]] = None,
            reference_group_id: Optional[Union[str, ObjectId]] = None,
            reference_id: Optional[Union[str, ObjectId]] = None,
            question_group_id: Optional[Union[str, ObjectId]] = None,
    ) -> List[QuestionEntry]:
        logger.info("Fetching question entries from database with filter")
        logger.debug("Building question entry query with provided filters.")
        
        query = {}
        
        if question is not None:
            query["question"] = {"$regex": re.escape(question), "$options": "i"}
            logger.debug(f"Filter applied: question contains '{question}'")
        
        if question_group_id is not None:
            query["question_group"] = as_object_id(str(question_group_id))
            logger.debug(f"Filter applied: question_group = {question_group_id}")
        
        if super_class is not None:
            query["classification.super_class"] = super_class
            logger.debug(f"Filter applied: super_class = {super_class}")
        
        if sub_class is not None:
            if super_class is None:
                logger.error(f"Cannot filter by sub_class without super_class.")
                raise ValueError("Cannot filter by sub_class without super_class.")
            query["classification.sub_class"] = sub_class
            logger.debug(f"Filter applied: sub_class = {sub_class}")
        
        included_reference_ids = []
        if reference_id is not None:
            ref = self.reference_service.get_reference_by_id(reference_id)
            stacked_filter_msg = []
            if guideline_id is not None:
                if ref.guideline_id != guideline_id:
                    logger.error(f"Reference ID {reference_id} does not match guideline ID {guideline_id}.")
                    raise ValueError(f"Reference ID {reference_id} does not match guideline ID {guideline_id}.")
                else:
                    stacked_filter_msg.append(f"with matching guideline ID={guideline_id}")
            if reference_group_id is not None:
                if ref.reference_group_id != reference_group_id:
                    logger.error(f"Reference ID {reference_id} does not match reference group ID {reference_group_id}.")
                    raise ValueError(
                        f"Reference ID {reference_id} does not match reference group ID {reference_group_id}.",
                    )
                else:
                    stacked_filter_msg.append(f"with matching reference group ID={reference_group_id}")
            
            msg = f"Filter applied: reference ID {reference_id}" + f" ({' and'.join(stacked_filter_msg)})" if stacked_filter_msg else ""
            logger.debug(msg)
            included_reference_ids = [as_object_id(str(reference_id))]
        elif (guideline_id is not None) or (reference_group_id is not None):
            refs = self.reference_service.get_all_references(
                guideline_id=guideline_id, reference_group_id=reference_group_id,
            )
            stacked_filter_msg = []
            if guideline_id is not None:
                stacked_filter_msg.append(f"guideline ID={guideline_id}")
            if reference_group_id is not None:
                stacked_filter_msg.append(f"reference group ID={reference_group_id}")
            msg = f"Filter applied: reference IDs with {' and'.join(stacked_filter_msg)}"
            logger.debug(msg)
            included_reference_ids = [as_object_id(str(ref.id)) for ref in refs]
        
        if included_reference_ids:
            query["expected_retrieval"] = {"$in": included_reference_ids}
        
        try:
            logger.info(f"Executing question-entry query: {query}")
            question_entries = list(self.dataset_collection.find(query))
            if len(question_entries) == 0:
                logger.warning("No question-entries found matching query.")
            else:
                logger.info(f"Successfully fetched {len(question_entries)} question-entries in dataset matching query.")
            results = [QuestionEntry(**doc) for doc in question_entries]
            return results
        except Exception as e:
            logger.error(f"Error executing question-entry query: {str(e)}")
            raise
    
    def delete_question_entry(self, question_entry_id: Union[str, ObjectId]) -> bool:
        logger.debug(f"Attempting to delete question-entry with ID: {question_entry_id}")
        obj_id = ObjectId(question_entry_id) if isinstance(question_entry_id, str) else question_entry_id
        
        # Check if entry exists
        if not self.dataset_collection.find_one({"_id": obj_id}):
            msg = f"Question entry with ID {question_entry_id} not found."
            logger.warning(msg)
            return True
        
        result = self.dataset_collection.delete_one({"_id": obj_id})
        
        if result.deleted_count > 0:
            logger.info(f"Successfully deleted question-entry with ID: {question_entry_id}")
            return True
        else:
            logger.warning(f"Failed to delete question-entry with ID: {question_entry_id}")
            raise ValueError(f"Failed to delete question-entry with ID: {question_entry_id}")
    
    def update_question_entry(
            self, question_entry_id: Union[str, ObjectId], update_data: QuestionEntry,
    ) -> QuestionEntry:
        logger.debug(f"Updating question-entry with ID: {question_entry_id}")
        obj_id = ObjectId(question_entry_id) if isinstance(question_entry_id, str) else question_entry_id
        
        # Build update the object from the supplied data (exclude unset fields for partial updates)
        update_fields = update_data.model_dump(exclude_unset=True)
        
        # Attempt the update
        result = self.dataset_collection.update_one(
            {"_id": obj_id},
            {"$set": update_fields},
        )
        if result.matched_count == 0:
            msg = f"Question entry with ID {question_entry_id} not found."
            logger.warning(msg)
            raise ValueError(msg)
        if result.modified_count == 0:
            msg = f"No changes made to the question entry with ID {question_entry_id}."
            logger.warning(msg)
            raise ValueError(msg)
        
        logger.info(f"Successfully updated question-entry with ID: {question_entry_id}")
        return self.get_question_entry_by_id(obj_id)
    
    def insert_new_question_group(self, question_group: QuestionGroup) -> QuestionGroup:
        logger.debug("Attempting to insert new question group.")
        data = question_group.model_dump(by_alias=True)
        data.pop("_id", None)
        
        try:
            result = self.question_group_collection.insert_one(data)
            logger.info(f"Inserted question group with ID {result.inserted_id}")
            return self.find_question_group(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to insert question group: {str(e)}", exc_info=True)
            raise
    
    def list_all_question_groups(self, group_name: Optional[str] = None) -> List[QuestionGroup]:
        logger.debug("Fetching all question groups.")
        query = {}
        if group_name:
            query["group_name"] = {"$regex": re.escpae(group_name), "$options": "i"}
            logger.debug(f"Filter applied: group_name contains '{group_name}'")
        
        try:
            docs = list(self.question_group_collection.find(query))
            logger.info(f"Fetched {len(docs)} question group(s).")
            return [QuestionGroup(**doc) for doc in docs]
        except Exception as e:
            logger.error(f"Error while listing question groups: {str(e)}")
            raise
    
    def find_question_group(self, question_group_entry_id: Union[str, ObjectId]) -> QuestionGroup:
        logger.debug(f"Searching for question group with ID {question_group_entry_id}")
        try:
            question_group = self.question_group_collection.find_one({"_id": as_object_id(question_group_entry_id)})
            if not question_group:
                logger.warning(f"Question group with ID {question_group_entry_id} not found.")
                raise ValueError(f"Question group not found for id: {str(question_group_entry_id)}")
            logger.info(f"Found question group with ID {question_group_entry_id}")
            return QuestionGroup(**question_group)
        except Exception as e:
            logger.error(f"Error fetching question group with ID {question_group_entry_id}: {str(e)}")
            raise
    
    def update_question_group(self, question_group_entry_id: Union[str, ObjectId], updated_question_group: QuestionGroup) -> QuestionGroup:
        logger.debug(f"Attempting to update question gorup with ID {question_group_entry_id}")
        try:
            current = self.question_group_collection.find_one({"_id": as_object_id(question_group_entry_id)})
            if not current:
                logger.warning(f"Question group with ID {question_group_entry_id} not found.")
                raise ValueError(f"Question group not found for id: {str(question_group_entry_id)}")
            
            update_data = updated_question_group.model_dump(by_alias=True, exclude_unset=True, exclude={"id"})
            changes = {k: v for k, v in update_data.items() if current.get(k) != v}
            
            if not changes:
                logger.info(f"No changes to apply for question group with ID {question_group_entry_id}")
                return QuestionGroup(**current)
            
            result = self.question_group_collection.update_one(
                {"_id": as_object_id(question_group_entry_id)},
                {"$set": changes},
            )
            if result.matched_count == 0:
                logger.error(f"Update failed: question group with ID {question_group_entry_id} not found.")
                raise ValueError(f"Question group not found for id: {str(question_group_entry_id)}")
            
            logger.info(f"Question group with ID {question_group_entry_id} updated: {list(changes.keys())}")
            return self.find_question_group(question_group_entry_id)
        except Exception as e:
            logger.error(f"Error updating question group with ID {question_group_entry_id}: {str(e)}")
            raise
    
    def delete_question_group(self, question_group_entry_id: Union[str, ObjectId]):
        logger.debug(f"Attempting to remove evaluation entries from to be deleted evaluator")
        try:
            to_be_del_entries = self.get_question_entries(question_group_id=question_group_entry_id)
            for question in to_be_del_entries:
                self.delete_question_entry(question.id)
        except Exception as e:
            logger.error(f"Error deleting questions for question gorup: {question_group_entry_id} -> {str(e)}", exc_info=True)
            raise
        
        logger.debug(f"Attempting to delete question group with ID {question_group_entry_id}")
        try:
            result = self.question_group_collection.delete_one({"_id": as_object_id(question_group_entry_id)})
            if result.deleted_count == 0:
                logger.warning(f"Question group with ID {question_group_entry_id} not found.")
                raise ValueError(f"Question group not found for id: {str(question_group_entry_id)}")
            logger.info(f"Deleted question group with ID {question_group_entry_id}")
        except Exception as e:
            logger.error(f"Error deleting question group with ID {question_group_entry_id}: {str(e)}", exc_info=True)
            raise
