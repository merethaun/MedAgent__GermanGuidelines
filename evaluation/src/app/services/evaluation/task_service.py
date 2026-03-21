from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from app.models.auth.user import CurrentUser
from app.models.evaluation.run import EvaluationRun, EvaluationSample
from app.models.evaluation.task import ManualReviewResult, ManualReviewSubmission, ManualReviewTask


@dataclass
class TaskService:
    collection: Collection

    def create_for_sample(
            self,
            *,
            run: EvaluationRun,
            sample: EvaluationSample,
            assignment_mode: str,
            assigned_evaluator_sub: Optional[str],
            assigned_evaluator_username: Optional[str],
    ) -> ManualReviewTask:
        task = ManualReviewTask(
            run_id=run.id,
            sample_id=sample.id,
            assignment_mode=assignment_mode,
            assigned_evaluator_sub=assigned_evaluator_sub,
            assigned_evaluator_username=assigned_evaluator_username,
        )
        payload = task.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)
        result = self.collection.insert_one(payload)
        return self.get_task(str(result.inserted_id))

    def get_task(self, task_id: str) -> ManualReviewTask:
        doc = self.collection.find_one({"_id": self._oid(task_id)})
        if not doc:
            raise ValueError(f"Manual review task not found: {task_id}")
        return ManualReviewTask.model_validate(doc)

    def list_tasks(
            self,
            *,
            user: Optional[CurrentUser] = None,
            run_id: Optional[str] = None,
            status: Optional[str] = None,
            mine: bool = False,
            include_open: bool = False,
    ) -> List[ManualReviewTask]:
        query = {}
        if run_id:
            query["run_id"] = str(run_id)
        if status:
            query["status"] = status
        if mine:
            if user is None:
                raise ValueError("user is required when mine=True")
            if include_open:
                query["$or"] = [
                    {"claimed_by_sub": user.sub},
                    {"status": "open", "$or": [{"assigned_evaluator_sub": None}, {"assigned_evaluator_sub": user.sub}]},
                ]
            else:
                query["claimed_by_sub"] = user.sub
        return [ManualReviewTask.model_validate(doc) for doc in self.collection.find(query).sort("created_at", 1)]

    def claim_task(self, task_id: str, user: CurrentUser) -> ManualReviewTask:
        now = datetime.now(timezone.utc)
        doc = self.collection.find_one_and_update(
            {
                "_id": self._oid(task_id),
                "status": "open",
                "$or": [
                    {"assigned_evaluator_sub": None},
                    {"assigned_evaluator_sub": user.sub},
                ],
            },
            {
                "$set": {
                    "status": "claimed",
                    "claimed_by_sub": user.sub,
                    "claimed_by_username": user.username,
                    "claimed_at": now,
                    "updated_at": now,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            raise ValueError("Task is not available to claim")
        return ManualReviewTask.model_validate(doc)

    def submit_task(self, task_id: str, user: CurrentUser, submission: ManualReviewSubmission) -> ManualReviewTask:
        existing = self.get_task(task_id)
        if existing.status == "completed":
            raise ValueError("Task is already completed")
        if existing.claimed_by_sub and existing.claimed_by_sub != user.sub:
            raise ValueError("Task is claimed by another evaluator")
        if existing.assigned_evaluator_sub and existing.assigned_evaluator_sub != user.sub:
            raise ValueError("Task is assigned to another evaluator")

        now = datetime.now(timezone.utc)
        factuality_ratio = None
        if submission.fact_count_overall is not None and submission.fact_count_overall > 0:
            factuality_ratio = (submission.fact_count_backed or 0) / submission.fact_count_overall

        review = ManualReviewResult(
            **submission.model_dump(),
            reviewer_sub=user.sub,
            reviewer_username=user.username,
            factuality_ratio=factuality_ratio,
            submitted_at=now,
        )
        doc = self.collection.find_one_and_update(
            {"_id": self._oid(task_id)},
            {
                "$set": {
                    "status": "completed",
                    "claimed_by_sub": user.sub,
                    "claimed_by_username": user.username,
                    "claimed_at": existing.claimed_at or now,
                    "completed_at": now,
                    "review": review.model_dump(),
                    "updated_at": now,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        return ManualReviewTask.model_validate(doc)

    def delete_for_samples(self, sample_ids: List[str]) -> int:
        if not sample_ids:
            return 0
        result = self.collection.delete_many({"sample_id": {"$in": sample_ids}})
        return result.deleted_count

    @staticmethod
    def _oid(raw_id: str) -> ObjectId:
        try:
            return ObjectId(raw_id)
        except Exception as exc:
            raise ValueError(f"Invalid task_id: {raw_id}") from exc
