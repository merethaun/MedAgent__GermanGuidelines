import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Union

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

from app.exceptions.system.chat import ChatNotFoundError
from app.models.system.system_chat_interaction import Chat, ChatInteraction, RetrievalResult
from app.services.system.workflow_system_interaction_service import WorkflowSystemInteractionService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class ChatService:
    """
    Service for:
    - CRUD operations for Chat documents
    - Interaction: append user question -> run workflow -> store response + retrieval outputs

    Notes:
    - This service should not depend on FastAPI.
    - This service uses MongoDB as persistence.
    """
    
    chat_collection: Collection
    workflow_interaction_service: WorkflowSystemInteractionService
    
    # ----------------------------
    # Helpers
    # ----------------------------
    @staticmethod
    def _to_object_id(value: Union[str, ObjectId], *, name: str) -> ObjectId:
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(value)
        except Exception as e:
            raise ChatNotFoundError(f"Invalid {name}: {value}") from e
    
    # ----------------------------
    # CRUD
    # ----------------------------
    def create_chat_entry(self, chat: Chat) -> Chat:
        """
        Insert a new chat document. Ensures `interactions` is an array.
        """
        payload = chat.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)  # let MongoDB generate the ObjectId
        
        # Ensure interactions exists as list in DB
        if payload.get("interactions") is None:
            payload["interactions"] = []
        
        logger.info("Creating chat entry")
        res: InsertOneResult = self.chat_collection.insert_one(payload)
        logger.info("Chat entry created: id=%s", str(res.inserted_id))
        
        return self.get_chat_entry_by_id(res.inserted_id)
    
    def get_chat_entry_by_id(self, chat_id: Union[str, ObjectId]) -> Chat:
        oid = self._to_object_id(chat_id, name="chat_id")
        doc = self.chat_collection.find_one({"_id": oid})
        if not doc:
            raise ChatNotFoundError(f"Chat entry not found: {str(oid)}")
        return Chat(**doc)
    
    def update_chat_entry(self, chat_id: Union[str, ObjectId], updated_chat: Chat) -> Chat:
        """
        Replace mutable fields via $set. Never attempts to set `_id`.
        """
        oid = self._to_object_id(chat_id, name="chat_id")
        
        payload = updated_chat.model_dump(by_alias=True, exclude_none=False)
        payload.pop("_id", None)  # critical: never $set the MongoDB _id
        
        logger.info("Updating chat entry: id=%s", str(oid))
        res: UpdateResult = self.chat_collection.update_one({"_id": oid}, {"$set": payload})
        
        if res.matched_count == 0:
            raise ChatNotFoundError(f"Chat entry not found: {str(oid)}")
        
        if res.modified_count == 0:
            logger.debug("No changes detected for chat: id=%s", str(oid))
        else:
            logger.info("Chat entry updated: id=%s", str(oid))
        
        return self.get_chat_entry_by_id(oid)
    
    def delete_chat_entry(self, chat_id: Union[str, ObjectId]) -> None:
        oid = self._to_object_id(chat_id, name="chat_id")
        logger.info("Deleting chat entry: id=%s", str(oid))
        res: DeleteResult = self.chat_collection.delete_one({"_id": oid})
        if res.deleted_count == 0:
            raise ChatNotFoundError(f"Chat entry not found: {str(oid)}")
    
    def list_chats(self, workflow_id: Optional[str] = None, user_name: Optional[str] = None) -> List[Chat]:
        """
        List chats with optional filters.
        """
        query: dict = {}
        
        if workflow_id is not None:
            query["workflow_system_id"] = self._to_object_id(workflow_id, name="workflow_id")
        
        if user_name is not None:
            query["username"] = {"$regex": re.escape(user_name), "$options": "i"}
        
        logger.info("Listing chats with query=%s", query)
        docs = list(self.chat_collection.find(query))
        return [Chat(**d) for d in docs]
    
    # ----------------------------
    # Interaction
    # ----------------------------
    def pose_question(self, chat_id: Union[str, ObjectId], user_input: str) -> Chat:
        """
        Append a new ChatInteraction (user_input) and generate/store the assistant response
        using the configured workflow system.

        Flow:
        1) Load chat
        2) Append interaction with user_input (+ timestamps)
        3) Persist chat (so the question is saved even if generation fails)
        4) Call workflow_interaction_service.generate_response(...)
        5) Store generator + retrieval output + latencies + execution trace
        6) Persist updated chat and return it
        """
        if not user_input.strip():
            raise ValueError("user_input must not be empty")
        
        oid = self._to_object_id(chat_id, name="chat_id")
        chat = self.get_chat_entry_by_id(oid)
        
        logger.info("Pose question in chat: id=%s chars=%d", str(oid), len(user_input))
        
        if chat.interactions is None:
            chat.interactions = []
        
        # Create interaction and persist immediately
        interaction = ChatInteraction(user_input=user_input)
        try:
            # If your model has this field, set it; otherwise ignore
            interaction.time_user_input = datetime.now(timezone.utc)  # type: ignore[attr-defined]
        except Exception:
            pass
        
        interaction.workflow_execution = []
        chat.interactions.append(interaction)
        chat = self.update_chat_entry(oid, chat)
        
        # Generate response via workflow
        logger.debug("Calling workflow generate_response: workflow_system_id=%s", str(chat.workflow_system_id))
        out = self.workflow_interaction_service.generate_response(chat.workflow_system_id, chat)
        
        # Keep your tuple contract (generator_output, retrieval_output, response_latency, retrieval_latency, execution)
        generator_output, retrieval_output, response_latency, retrieval_latency, execution = out
        
        logger.debug(
            "Workflow result: generator_chars=%s retrieval_n=%s response_latency=%.2fs retrieval_latency=%s",
            len(generator_output) if generator_output else 0,
            len(retrieval_output) if retrieval_output else 0,
            float(response_latency) if response_latency is not None else 0.0,
            f"{retrieval_latency:.2f}s" if retrieval_latency is not None else "/",
        )
        
        # Attach outputs to the last interaction (the one we just appended)
        last = chat.interactions[-1]
        last.generator_output = generator_output
        
        last.retrieval_output = (
            [RetrievalResult(**r) if isinstance(r, dict) else r for r in retrieval_output]
            if retrieval_output
            else []
        )
        
        last.time_response_output = datetime.now(timezone.utc)
        last.retrieval_latency = retrieval_latency
        last.workflow_execution = execution
        
        chat = self.update_chat_entry(oid, chat)
        return chat
