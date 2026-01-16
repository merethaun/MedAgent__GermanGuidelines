import re
from datetime import date, datetime
from typing import List, Optional

from pymongo.collection import Collection

from app.exceptions.knowledge.guidelines import GuidelineNotFoundError
from app.models.knowledge.guidelines import GuidelineEntry
from app.utils.knowledge.mongodb_object_id import as_object_id
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class GuidelineService:
    """
    Service layer to manage CRUD operations for Guideline entries.
    """
    
    def __init__(self, guideline_collection: Collection):
        """
        Initialize the service with the MongoDB collection.
        """
        self.collection = guideline_collection
    
    def create_guideline(self, guideline: GuidelineEntry) -> GuidelineEntry:
        """
        Insert a new guideline into the database.

        Args:
            guideline: GuidelineEntry object.

        Returns:
            The inserted GuidelineEntry object with ID.
        """
        logger.debug("Attempting to create new guideline")
        data = guideline.model_dump(by_alias=True)
        if data.get('_id') is None:
            data.pop('_id', None)
        logger.debug(f"Prepared guideline data: {data}")
        
        try:
            result = self.collection.insert_one(data)
            logger.info(f"Created new guideline with ID {result.inserted_id}")
            return self.get_guideline_by_id(str(result.inserted_id))
        except Exception as e:
            logger.error(f"Failed to create guideline: {str(e)}")
            raise
    
    def get_guideline_by_id(self, object_id: str) -> GuidelineEntry:
        """
        Fetch a single guideline by its ID.

        Args:
            object_id: The ID of the guideline.

        Returns:
            A GuidelineEntry object or None if not found.
        """
        logger.debug(f"Attempting to fetch guideline with ID {object_id}")
        try:
            guideline = self.collection.find_one({"_id": as_object_id(object_id)})
            if guideline:
                logger.info(f"Successfully fetched guideline with ID {object_id}")
                return GuidelineEntry(**guideline)
            else:
                logger.warning(f"Guideline with ID {object_id} not found.")
                raise GuidelineNotFoundError(guideline_id=object_id)
        except Exception as e:
            logger.error(f"Error fetching guideline with ID {object_id}: {str(e)}")
            raise
    
    def get_all_guidelines(
            self,
            valid: Optional[bool] = None,
            extended_validity: Optional[bool] = None,
            is_living_guideline: Optional[bool] = None,
            leading_organizations: Optional[List[str]] = None,
            organizations: Optional[List[str]] = None,
            keyword_all: Optional[List[str]] = None,
            keyword_any: Optional[List[str]] = None,
            awmf_register_number: Optional[str] = None,
            awmf_register_number_full: Optional[str] = None,
            awmf_class: Optional[str] = None,
            publication_range_start: Optional[datetime] = None,
            publication_range_end: Optional[datetime] = None,
            download_range_start: Optional[date] = None,
            download_range_end: Optional[date] = None,
            missing_pdf: Optional[bool] = None,
    ) -> List[GuidelineEntry]:
        """
        Fetch all guidelines, optionally filtered by multiple parameters.

        Returns:
            A list of GuidelineEntry objects.
        """
        logger.info("Starting guideline search with filters")
        logger.debug("Building guideline query with provided filters.")
        
        query = {}
        
        if valid is not None:
            query["validity_information.valid"] = valid
            logger.debug(f"Filter applied: validity = {valid}")
        
        if extended_validity is not None:
            query["validity_information.extended_validity"] = extended_validity
            logger.debug(f"Filter applied: extended_validity = {extended_validity}")
        
        if is_living_guideline is not None:
            if is_living_guideline:
                query["validity_information.validity_range"] = 1
            else:
                query["validity_information.validity_range"] = {"$ne": 1}
            logger.debug(f"Filter applied: is_living_guideline = {is_living_guideline}")
        
        if leading_organizations:
            query["$and"] = [
                {
                    "publishing_organizations": {
                        "$elemMatch": {"$and": [{"name": {"$regex": re.escape(org), "$options": "i"}}, {"is_leading": True}]},
                    },
                }
                for org in leading_organizations
            ]
            logger.debug(f"Filter applied: leading organizations: {', '.join(leading_organizations)}")
        if organizations:
            query["$and"] = query["$and"] if "$and" in query else []
            query["$and"].extend(
                [
                    {'publishing_organizations.name': {'$regex': re.escape(org), '$options': 'i'}}
                    for org in organizations
                ],
            )
            logger.debug(f"Filter applied: organizations: {', '.join(organizations)}")
        
        if keyword_all:
            if isinstance(keyword_all, list):
                query["keywords"] = {"$all": keyword_all}
                logger.debug(f"Filter applied: all keywords {keyword_all}")
            else:
                logger.warning("keyword_all provided but is not a list. Ignoring filter.")
        
        if keyword_any:
            if isinstance(keyword_any, list):
                query["keywords"] = {"$in": keyword_any}
                logger.debug(f"Filter applied: any keyword {keyword_any}")
            else:
                logger.warning("keyword_any provided but is not a list. Ignoring filter.")
        
        if awmf_register_number:
            match = re.match(r"(\d{3}-\d{3})", awmf_register_number)
            if match:
                formatted_short = match.group(1)
                query["awmf_register_number"] = formatted_short
                logger.debug(f"Filter applied: awmf_register_number = {formatted_short}")
            else:
                logger.warning(f"Invalid awmf_register_number format: '{awmf_register_number}'. Ignoring filter.")
        
        if awmf_register_number_full:
            query["awmf_register_number_full"] = {"$regex": re.escape(awmf_register_number_full), "$options": "i"}
            logger.debug(f"Filter applied: awmf_register_number contains '{awmf_register_number_full}'")
        
        if awmf_class:
            query["awmf_class"] = awmf_class
            logger.debug(f"Filter applied: awmf_class = {awmf_class}")
        
        if publication_range_start or publication_range_end:
            pub_query = {}
            if publication_range_start:
                pub_query["$gte"] = publication_range_start
            if publication_range_end:
                pub_query["$lte"] = publication_range_end
            query["validity_information.guideline_creation_date"] = pub_query
            print_start = publication_range_start if publication_range_start else '...'
            print_end = publication_range_end if publication_range_end else '...'
            logger.debug(f"Filter applied: publication_date {print_start} - {print_end}")
        
        if download_range_start or download_range_end:
            download_query = {}
            if download_range_start:
                download_query["$gte"] = download_range_start
            if download_range_end:
                download_query["$lte"] = download_range_end
            query["download_information.download_date"] = download_query
            print_start = download_range_start if download_range_start else '...'
            print_end = download_range_end if download_range_end else '...'
            logger.debug(f"Filter applied: download_date {print_start} - {print_end}")
        
        if missing_pdf is not None:
            if missing_pdf:
                query["$or"] = [
                    {"download_information.file_path": {"$exists": False}}, {"download_information.file_path": None},
                ]
                logger.debug("Filter applied: guidelines missing uploaded PDF.")
            else:
                query["$and"] = [
                    {"download_information.file_path": {"$exists": True}},
                    {"download_information.file_path": {"$ne": None}},
                ]
                logger.debug("Filter applied: guidelines with uploaded PDF.")
        
        try:
            logger.info(f"Executing guideline query: {query}")
            guidelines = list(self.collection.find(query))
            if len(guidelines) == 0:
                logger.warning("No guidelines found matching query.")
            else:
                logger.info(f"Successfully fetched {len(guidelines)} guidelines matching query.")
            results = [GuidelineEntry(**doc) for doc in guidelines]
            return results
        except Exception as e:
            logger.error(f"Error executing guideline query: {str(e)}")
            raise
    
    def update_guideline(self, object_id: str, updated_guideline: GuidelineEntry) -> GuidelineEntry:
        """ Update an existing guideline, automatically detecting fields that need to be updated.
        Args:
            object_id: The ID of the guideline to update.
            updated_guideline: The new GuidelineEntry object containing updated data.

        Returns:
            The updated GuidelineEntry object.
        """
        logger.debug(f"Attempting to update guideline with ID {object_id}")
        try:
            current_guideline = self.collection.find_one({"_id": as_object_id(object_id)})
            if not current_guideline:
                logger.warning(f"Guideline with ID {object_id} not found.")
                raise GuidelineNotFoundError(guideline_id=object_id)
            
            updated_data = updated_guideline.model_dump(by_alias=True, exclude_unset=True, exclude={"id"})
            fields_to_update = {k: v for k, v in updated_data.items() if current_guideline.get(k) != v}
            
            if not fields_to_update:
                logger.info(f"No changes detected for guideline with ID {object_id}.")
                return self.get_guideline_by_id(object_id)
            
            result = self.collection.update_one(
                {"_id": as_object_id(object_id)}, {"$set": fields_to_update}, )
            if result.matched_count == 0:
                logger.error(f"Failed to update guideline with ID {object_id}.")
                raise GuidelineNotFoundError(guideline_id=object_id)
            
            logger.info(
                f"Successfully updated guideline with ID {object_id}. Updated fields: {list(fields_to_update.keys())}",
            )
            return self.get_guideline_by_id(object_id)
        
        except Exception as e:
            logger.error(f"Error updating guideline with ID {object_id}: {str(e)}")
            raise
    
    def delete_guideline(self, object_id: str) -> bool:
        """
        Delete a guideline by its ID.

        Args:
            object_id: The ID of the guideline to delete.

        Returns:
            True if deletion was successful, False otherwise.
        """
        logger.debug(f"Attempting to delete guideline with ID {object_id}")
        try:
            result = self.collection.delete_one({"_id": as_object_id(object_id)})
            if result.deleted_count == 0:
                logger.warning(f"Guideline with ID {object_id} not found.")
                raise GuidelineNotFoundError(guideline_id=object_id)
            logger.info(f"Successfully deleted guideline with ID {object_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting guideline with ID {object_id}: {str(e)}")
            raise
