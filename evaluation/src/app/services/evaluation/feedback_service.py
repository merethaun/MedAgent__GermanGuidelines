from dataclasses import dataclass

from pymongo.collection import Collection

from app.models.auth.user import CurrentUser
from app.models.evaluation.feedback import AnswerFeedbackCreateRequest, AnswerFeedbackEntry
from app.services.backend_api_client import BackendApiClient


@dataclass
class FeedbackService:
    collection: Collection
    backend_client: BackendApiClient

    def create_feedback(self, request: AnswerFeedbackCreateRequest, user: CurrentUser, access_token: str) -> AnswerFeedbackEntry:
        chat = self.backend_client.get_chat(request.chat_id, access_token)
        interactions = chat.get("interactions") or []
        if request.interaction_index < 0 or request.interaction_index >= len(interactions):
            raise ValueError("interaction_index is out of range")
        interaction = interactions[request.interaction_index]

        feedback = AnswerFeedbackEntry(
            user_sub=user.sub,
            username=user.username,
            chat_id=request.chat_id,
            interaction_index=request.interaction_index,
            helpful=request.helpful,
            rating=request.rating,
            comment=request.comment,
            question_text=interaction.get("user_input"),
            answer_text=interaction.get("generator_output"),
            workflow_system_id=chat.get("workflow_system_id"),
            retrieval_output=interaction.get("retrieval_output") or [],
        )
        payload = feedback.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)
        result = self.collection.insert_one(payload)
        return AnswerFeedbackEntry.model_validate(self.collection.find_one({"_id": result.inserted_id}))

    def count_for_sample_chat(self, chat_id: str, interaction_index: int) -> int:
        return self.collection.count_documents({"chat_id": chat_id, "interaction_index": interaction_index})
