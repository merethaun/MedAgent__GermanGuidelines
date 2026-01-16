import re
from datetime import datetime, timezone
from typing import List, Union, Optional

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.results import InsertOneResult, DeleteResult, UpdateResult

from app.models.chat.chat import Chat, ChatInteraction, RetrievalResult
from app.services.system import WorkflowSystemInteractionService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ChatService:
    """
    Service layer to manage CRUD operations for chats AND providing interaction possibility with chat.
    """
    
    def __init__(self, chat_collection: Collection, workflow_interaction_service: WorkflowSystemInteractionService):
        self.chat_collection = chat_collection
        self.workflow_interaction_service = workflow_interaction_service
    
    def create_chat_entry(self, chat: Chat) -> Chat:
        logger.debug(f"Creating chat")
        
        data = chat.model_dump(by_alias=True, exclude_unset=True)
        if data.get("interactions", None) is None:
            data["interactions"] = []
        result: InsertOneResult = self.chat_collection.insert_one(data)
        
        entry = self.get_chat_entry_by_id(result.inserted_id)
        
        logger.info(f"Chat entry created with ID: {result.inserted_id}")
        return entry
    
    def get_chat_entry_by_id(self, chat_id: Union[str, ObjectId]) -> Chat:
        chat_oid = ObjectId(chat_id) if isinstance(chat_id, str) else chat_id
        entry = self.chat_collection.find_one({"_id": chat_oid})
        
        if not entry:
            raise ValueError(f"Chat entry not found: {chat_oid}")
        
        return Chat(**entry)
    
    def pose_question(self, chat_id: Union[str, ObjectId], user_input: str) -> Chat:
        logger.info(f"Pose question '{user_input}' in chat with ID: {chat_id}")
        chat = self.get_chat_entry_by_id(chat_id)
        
        if not chat.interactions:
            chat.interactions = []
        chat.interactions.append(ChatInteraction(user_input=user_input))
        chat.interactions[-1].workflow_execution = []
        chat = self.update_chat_entry(chat_id, chat)
        
        ## Response generation
        logger.debug(f"Pose question '{user_input}' to workflow with ID: {chat.workflow_system_id}")
        out = self.workflow_interaction_service.generate_response(chat.workflow_system_id, chat)
        generator_output, retrieval_output = out[0], out[1]
        response_latency, retrieval_latency, execution = out[2], out[3], out[4]
        
        ## Store result
        logger.debug(
            f"Response: generator={len(generator_output) if generator_output else '/'} chars, "
            f"retrieval={len(retrieval_output) if retrieval_output else '/'}, "
            f"response_latency={response_latency:.2f}, "
            f"retrieval_latency={f'{retrieval_latency:.2f}' if retrieval_latency is not None else '/'}, ",
        )
        
        chat.interactions[-1].generator_output = generator_output
        chat.interactions[-1].retrieval_output = [
            RetrievalResult(**r) if isinstance(r, dict) else r for r in retrieval_output
        ] if retrieval_output else []
        chat.interactions[-1].time_response_output = datetime.now(timezone.utc)
        chat.interactions[-1].retrieval_latency = retrieval_latency
        chat.interactions[-1].workflow_execution = execution
        
        chat = self.update_chat_entry(chat_id, chat)
        
        return chat
    
    def update_chat_entry(self, chat_id: Union[str, ObjectId], updated_chat: Chat) -> Chat:
        chat_oid = ObjectId(chat_id) if isinstance(chat_id, str) else chat_id
        logger.info(f"Updating chat entry with ID: {chat_oid}")
        
        data = updated_chat.model_dump(by_alias=True)
        result: UpdateResult = self.chat_collection.update_one({"_id": chat_oid}, {"$set": data})
        
        if result.modified_count > 0:
            logger.info(f"Chat entry updated.")
        else:
            logger.warning(f"No chat entry updated for ID: {chat_oid}")
        
        entry = self.get_chat_entry_by_id(chat_oid)
        return entry
    
    def delete_chat_entry(self, chat_id: Union[str, ObjectId]) -> DeleteResult:
        chat_oid = ObjectId(chat_id) if isinstance(chat_id, str) else chat_id
        logger.info(f"Deleting chat entry with ID: {chat_oid}")
        
        result: DeleteResult = self.chat_collection.delete_one({"_id": chat_oid})
        return result
    
    def list_all_chats(self, workflow_id: Optional[str], user_name: Optional[str]) -> List[Chat]:
        logger.info("Starting chat search with filters")
        logger.debug("Building chat query with provided filters.")
        
        query = {}
        
        if workflow_id is not None:
            query["workflow_system_id"] = ObjectId(workflow_id)
            logger.debug(f"Filter applied: workflow_system_id = {workflow_id}")
        
        if user_name is not None:
            query["username"] = {"$regex": re.escape(user_name), "$options": "i"}
            logger.debug(f"Filter applied: username contains '{user_name}'")
        
        try:
            logger.info(f"Executing chat query: {query}")
            all_chats = list(self.chat_collection.find(query))
            if len(all_chats) == 0:
                logger.warning("No chats found matching query.")
            else:
                logger.info(f"Successfully fetched {len(all_chats)} chats matching query.")
            results = [Chat(**chat) for chat in all_chats]
            return results
        except Exception as e:
            logger.error(f"Error executing chats query: {str(e)}")
            raise
