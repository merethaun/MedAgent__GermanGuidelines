from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from pymongo.collection import Collection

from app.models.auth.user import CurrentUser
from app.models.evaluation.evaluator import EvaluatorProfile


@dataclass
class EvaluatorProfileService:
    collection: Collection

    def upsert_from_user(self, user: CurrentUser) -> EvaluatorProfile:
        payload = {
            "sub": user.sub,
            "username": user.username,
            "last_seen_at": datetime.now(timezone.utc),
        }
        self.collection.update_one({"sub": user.sub}, {"$set": payload}, upsert=True)
        return self.get_by_sub(user.sub)

    def get_by_sub(self, sub: str) -> EvaluatorProfile:
        doc = self.collection.find_one({"sub": sub})
        if not doc:
            raise ValueError(f"Evaluator profile not found: {sub}")
        return EvaluatorProfile.model_validate(doc)

    def list_profiles(self) -> List[EvaluatorProfile]:
        return [EvaluatorProfile.model_validate(doc) for doc in self.collection.find({}).sort("username", 1)]
