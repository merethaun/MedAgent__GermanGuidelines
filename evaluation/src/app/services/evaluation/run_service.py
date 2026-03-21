import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.collection import Collection

from app.models.auth.user import CurrentUser
from app.models.evaluation.run import EvaluationRun, EvaluationRunCreateRequest, EvaluationSample
from app.services.backend_api_client import BackendApiClient
from app.services.evaluation.dataset_service import DatasetService
from app.services.evaluation.feedback_service import FeedbackService
from app.services.evaluation.metric_service import MetricService
from app.services.evaluation.task_service import TaskService
from app.utils.logging import setup_logger

logger = setup_logger(__name__)
RUNTIME_LLM_SETTINGS_FIELD = "_runtime_llm_settings"
RUN_ACCESS_TOKEN_FIELD = "_run_access_token"


@dataclass
class RunService:
    run_collection: Collection
    sample_collection: Collection
    dataset_service: DatasetService
    backend_client: BackendApiClient
    metric_service: MetricService
    task_service: TaskService
    feedback_service: FeedbackService
    _worker_task: Optional[asyncio.Task] = field(default=None, init=False, repr=False)
    _stop_worker: bool = field(default=False, init=False, repr=False)

    def start_worker(self) -> None:
        if self._worker_task is None:
            self._stop_worker = False
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop_worker(self) -> None:
        self._stop_worker = True
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None

    async def _worker_loop(self) -> None:
        while not self._stop_worker:
            try:
                self.process_queued_runs_once()
            except Exception as exc:
                logger.error("Evaluation worker iteration failed: %s", str(exc), exc_info=True)
            await asyncio.sleep(2)

    def create_run(self, request: EvaluationRunCreateRequest, user: CurrentUser, access_token: str) -> EvaluationRun:
        workflow = self.backend_client.get_workflow(request.workflow_system_id, access_token)
        run = EvaluationRun(
            name=request.name,
            workflow_system_id=request.workflow_system_id,
            workflow_name=workflow.get("name"),
            source_type=request.source_type,
            question_group_id=request.question_group_id,
            question_group_name=self._question_group_name(request.question_group_id),
            source_chat_id=request.source_chat_id,
            source_interaction_index=request.source_interaction_index,
            manual_review_mode=request.manual_review_mode,
            assigned_evaluator_sub=request.assigned_evaluator_sub,
            assigned_evaluator_username=request.assigned_evaluator_username,
            manual_review_assignments=request.manual_review_assignments,
            created_by_sub=user.sub,
            created_by_username=user.username,
        )
        payload = run.model_dump(by_alias=True, exclude_none=True)
        payload.pop("_id", None)
        payload[RUN_ACCESS_TOKEN_FIELD] = access_token
        if request.runtime_llm_settings is not None:
            payload[RUNTIME_LLM_SETTINGS_FIELD] = request.runtime_llm_settings.model_dump(exclude_none=True)
        result = self.run_collection.insert_one(payload)
        stored_run = self.get_run(str(result.inserted_id))
        self._create_initial_samples(stored_run, request)
        return self.refresh_run_counts(str(stored_run.id))

    def list_runs(self) -> List[EvaluationRun]:
        return [EvaluationRun.model_validate(doc) for doc in self.run_collection.find({}).sort("created_at", -1)]

    def get_run(self, run_id: str) -> EvaluationRun:
        doc = self.run_collection.find_one({"_id": self._oid(run_id, "run_id")})
        if not doc:
            raise ValueError(f"Evaluation run not found: {run_id}")
        return EvaluationRun.model_validate(doc)

    def get_sample(self, sample_id: str) -> EvaluationSample:
        doc = self.sample_collection.find_one({"_id": self._oid(sample_id, "sample_id")})
        if not doc:
            raise ValueError(f"Evaluation sample not found: {sample_id}")
        return EvaluationSample.model_validate(doc)

    def rerun_run(self, run_id: str, access_token: str) -> EvaluationRun:
        run = self.get_run(run_id)
        self._ensure_run_is_idle(run)
        samples = self.list_samples(run_id=run_id)
        if not samples:
            raise ValueError(f"Evaluation run has no samples to rerun: {run_id}")
        self._reset_samples_for_rerun(samples)
        self._queue_run_for_processing(run.id, access_token)
        return self.refresh_run_counts(run_id)

    def rerun_sample(self, sample_id: str, access_token: str) -> EvaluationSample:
        sample = self.get_sample(sample_id)
        run = self.get_run(str(sample.run_id))
        self._ensure_run_is_idle(run)
        self._reset_samples_for_rerun([sample])
        self._queue_run_for_processing(run.id, access_token)
        self.refresh_run_counts(str(run.id))
        return self.get_sample(sample_id)

    def list_samples(
            self,
            *,
            run_id: Optional[str] = None,
            status: Optional[str] = None,
    ) -> List[EvaluationSample]:
        query: Dict[str, Any] = {}
        if run_id:
            query["run_id"] = str(run_id)
        if status:
            query["status"] = status
        return [EvaluationSample.model_validate(doc) for doc in self.sample_collection.find(query).sort("created_at", 1)]

    def process_queued_runs_once(self) -> None:
        queued_runs = list(self.run_collection.find({"status": {"$in": ["queued", "running"]}}).sort("created_at", 1))
        for doc in queued_runs:
            self._process_run(
                EvaluationRun.model_validate(doc),
                access_token=doc.get(RUN_ACCESS_TOKEN_FIELD),
                runtime_llm_settings=doc.get(RUNTIME_LLM_SETTINGS_FIELD),
            )

    def _create_initial_samples(self, run: EvaluationRun, request: EvaluationRunCreateRequest) -> None:
        samples: List[EvaluationSample] = []
        if request.source_type == "question_group_batch":
            questions = self.dataset_service.list_questions(question_group_id=request.question_group_id)
            for question in questions:
                samples.append(
                    EvaluationSample(
                        run_id=run.id,
                        source_type="question_group_batch",
                        source_question_id=str(question.id),
                        source_question_group_id=request.question_group_id,
                        workflow_system_id=run.workflow_system_id,
                        workflow_name=run.workflow_name,
                        question_text=question.question,
                        question_classification=question.classification,
                        expected_answer=question.correct_answer,
                        expected_retrieval=question.expected_retrieval,
                    ),
                )
        else:
            samples.append(
                EvaluationSample(
                    run_id=run.id,
                    source_type="chat_snapshot",
                    source_chat_id=request.source_chat_id,
                    source_interaction_index=request.source_interaction_index,
                    workflow_system_id=run.workflow_system_id,
                    workflow_name=run.workflow_name,
                ),
            )

        for sample in samples:
            payload = sample.model_dump(by_alias=True, exclude_none=True)
            payload.pop("_id", None)
            self.sample_collection.insert_one(payload)

        self.refresh_run_counts(str(run.id))

    def _process_run(
            self,
            run: EvaluationRun,
            access_token: Optional[str],
            runtime_llm_settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not access_token:
            logger.error("Run %s has no stored user access token for backend execution", str(run.id))
            self._finalize_run(run.id, "failed")
            return

        samples = self.list_samples(run_id=str(run.id))
        if not samples:
            self._finalize_run(run.id, "failed")
            return

        self._update_run(run.id, {"status": "running", "updated_at": datetime.now(timezone.utc)})
        try:
            for sample in samples:
                if sample.status in {"completed", "failed"}:
                    continue
                self._process_sample(
                    run,
                    sample,
                    access_token,
                    runtime_llm_settings=runtime_llm_settings,
                )

            refreshed = self.refresh_run_counts(str(run.id))
            if refreshed.failed_samples and refreshed.processed_samples == refreshed.total_samples:
                final_status = "partial"
            elif refreshed.processed_samples == refreshed.total_samples:
                final_status = "completed"
            else:
                final_status = "running"

            if final_status == "running":
                self._update_run(run.id, {"status": final_status, "updated_at": datetime.now(timezone.utc)})
            else:
                self._finalize_run(run.id, final_status)
        except Exception:
            self._finalize_run(run.id, "failed")
            raise

    def _process_sample(
            self,
            run: EvaluationRun,
            sample: EvaluationSample,
            access_token: str,
            runtime_llm_settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._update_sample(sample.id, {"status": "running", "updated_at": datetime.now(timezone.utc)})
        try:
            if sample.source_type == "question_group_batch":
                updated = self._process_question_batch_sample(
                    run,
                    sample,
                    access_token,
                    runtime_llm_settings=runtime_llm_settings,
                )
            else:
                updated = self._process_chat_snapshot_sample(run, sample, access_token)
            metrics = self.metric_service.compute_for_sample(
                updated,
                access_token,
                llm_settings_override=runtime_llm_settings,
            )
            updated = self._persist_sample_result(updated, {"automatic_metrics": metrics.model_dump(), "status": "completed"})
            self._maybe_create_manual_review_task(run, updated)
        except Exception as exc:
            logger.error("Sample processing failed for sample %s: %s", str(sample.id), str(exc), exc_info=True)
            self._persist_sample_result(sample, {"status": "failed", "failure_reason": str(exc)})
        self.refresh_run_counts(str(run.id))

    def _process_question_batch_sample(
            self,
            run: EvaluationRun,
            sample: EvaluationSample,
            access_token: str,
            runtime_llm_settings: Optional[Dict[str, Any]] = None,
    ) -> EvaluationSample:
        chat = self.backend_client.create_chat(
            run.workflow_system_id,
            access_token=access_token,
            username=run.created_by_username or f"evaluation-run:{run.name}",
            name=f"Evaluation run {run.name}",
        )
        answered = self.backend_client.pose_question(
            chat["_id"],
            sample.question_text or "",
            access_token=access_token,
            runtime_llm_settings=runtime_llm_settings,
        )
        interactions = answered.get("interactions") or []
        if not interactions:
            raise ValueError("Backend chat returned no interactions")
        interaction = interactions[-1]
        update = {
            "backend_chat_id": str(answered.get("_id")),
            "backend_interaction_index": len(interactions) - 1,
            "answer_text": interaction.get("generator_output"),
            "retrieval_output": interaction.get("retrieval_output") or [],
            "response_latency": self._response_latency_from_interaction(interaction),
            "retrieval_latency": interaction.get("retrieval_latency"),
            "workflow_execution": interaction.get("workflow_execution") or [],
            "failure_reason": None,
        }
        return self._persist_sample_result(sample, update)

    def _process_chat_snapshot_sample(self, run: EvaluationRun, sample: EvaluationSample, access_token: str) -> EvaluationSample:
        chat = self.backend_client.get_chat(sample.source_chat_id or "", access_token)
        interactions = chat.get("interactions") or []
        index = sample.source_interaction_index or 0
        if index < 0 or index >= len(interactions):
            raise ValueError("Chat interaction index is out of range")
        interaction = interactions[index]
        update = {
            "question_text": interaction.get("user_input"),
            "backend_chat_id": sample.source_chat_id,
            "backend_interaction_index": index,
            "answer_text": interaction.get("generator_output"),
            "retrieval_output": interaction.get("retrieval_output") or [],
            "response_latency": self._response_latency_from_interaction(interaction),
            "retrieval_latency": interaction.get("retrieval_latency"),
            "workflow_execution": interaction.get("workflow_execution") or [],
            "workflow_system_id": chat.get("workflow_system_id"),
            "failure_reason": None,
            "user_feedback_count": self.feedback_service.count_for_sample_chat(sample.source_chat_id or "", index),
        }
        return self._persist_sample_result(sample, update)

    def _maybe_create_manual_review_task(self, run: EvaluationRun, sample: EvaluationSample) -> None:
        if run.manual_review_mode == "none" or sample.manual_review_task_id:
            return

        assignment_mode = "open"
        assigned_sub = None
        assigned_username = None
        if run.manual_review_mode == "assigned":
            assignment_mode = "assigned"
            assigned_sub = run.assigned_evaluator_sub
            assigned_username = run.assigned_evaluator_username
        elif run.manual_review_mode == "mixed":
            for assignment in run.manual_review_assignments:
                if assignment.question_id and assignment.question_id == sample.source_question_id:
                    assignment_mode = "assigned"
                    assigned_sub = assignment.evaluator_sub
                    assigned_username = assignment.evaluator_username
                    break
            if assignment_mode != "assigned" and run.source_type == "chat_snapshot" and run.assigned_evaluator_sub:
                assignment_mode = "assigned"
                assigned_sub = run.assigned_evaluator_sub
                assigned_username = run.assigned_evaluator_username

        task = self.task_service.create_for_sample(
            run=run,
            sample=sample,
            assignment_mode=assignment_mode,
            assigned_evaluator_sub=assigned_sub,
            assigned_evaluator_username=assigned_username,
        )
        self._update_sample(sample.id, {"manual_review_task_id": str(task.id), "updated_at": datetime.now(timezone.utc)})

    def refresh_run_counts(self, run_id: str) -> EvaluationRun:
        run_oid = self._oid(run_id, "run_id")
        run_ref = str(run_id)
        total_samples = self.sample_collection.count_documents({"run_id": run_ref})
        successful_samples = self.sample_collection.count_documents({"run_id": run_ref, "status": "completed"})
        failed_samples = self.sample_collection.count_documents({"run_id": run_ref, "status": "failed"})
        open_tasks = self.task_service.collection.count_documents({"run_id": run_ref, "status": {"$in": ["open", "claimed"]}})
        self.run_collection.update_one(
            {"_id": run_oid},
            {
                "$set": {
                    "total_samples": total_samples,
                    "processed_samples": successful_samples + failed_samples,
                    "failed_samples": failed_samples,
                    "open_tasks": open_tasks,
                    "updated_at": datetime.now(timezone.utc),
                },
            },
        )
        return self.get_run(run_id)

    def _question_group_name(self, question_group_id: Optional[str]) -> Optional[str]:
        if not question_group_id:
            return None
        return self.dataset_service.get_question_group(question_group_id).name

    def _ensure_run_is_idle(self, run: EvaluationRun) -> None:
        if run.status in {"queued", "running"}:
            raise ValueError("Evaluation run is already in progress")

    def _queue_run_for_processing(self, run_id: ObjectId, access_token: str) -> None:
        self.run_collection.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "queued",
                    "updated_at": datetime.now(timezone.utc),
                    RUN_ACCESS_TOKEN_FIELD: access_token,
                },
            },
        )

    def _reset_samples_for_rerun(self, samples: List[EvaluationSample]) -> None:
        sample_ids = [sample.id for sample in samples if sample.id is not None]
        if not sample_ids:
            raise ValueError("No samples are available to rerun")

        self.task_service.delete_for_samples([str(sample_id) for sample_id in sample_ids])
        now = datetime.now(timezone.utc)
        self.sample_collection.update_many(
            {"_id": {"$in": sample_ids}},
            {
                "$set": {
                    "status": "queued",
                    "backend_chat_id": None,
                    "backend_interaction_index": None,
                    "answer_text": None,
                    "retrieval_output": [],
                    "response_latency": None,
                    "retrieval_latency": None,
                    "workflow_execution": [],
                    "failure_reason": None,
                    "automatic_metrics": {"retrieval": {}},
                    "manual_review_task_id": None,
                    "updated_at": now,
                },
            },
        )

    def _update_run(self, run_id: ObjectId, update: Dict[str, Any]) -> None:
        self.run_collection.update_one({"_id": run_id}, {"$set": update})

    def _finalize_run(self, run_id: ObjectId, status: str) -> None:
        self.run_collection.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$unset": {
                    RUN_ACCESS_TOKEN_FIELD: "",
                },
            },
        )

    def _update_sample(self, sample_id: ObjectId, update: Dict[str, Any]) -> None:
        self.sample_collection.update_one({"_id": sample_id}, {"$set": update})

    def _persist_sample_result(self, sample: EvaluationSample, update: Dict[str, Any]) -> EvaluationSample:
        update["updated_at"] = datetime.now(timezone.utc)
        self._update_sample(sample.id, update)
        return self.get_sample(str(sample.id))

    @staticmethod
    def _response_latency_from_interaction(interaction: Dict[str, Any]) -> Optional[float]:
        start = interaction.get("time_question_input")
        end = interaction.get("time_response_output")
        if not start or not end:
            return None
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except AttributeError:
            if isinstance(start, datetime) and isinstance(end, datetime):
                start_dt = start
                end_dt = end
            else:
                return None
        return (end_dt - start_dt).total_seconds()

    @staticmethod
    def _oid(raw_id: str, label: str) -> ObjectId:
        try:
            return ObjectId(raw_id)
        except Exception as exc:
            raise ValueError(f"Invalid {label}: {raw_id}") from exc
