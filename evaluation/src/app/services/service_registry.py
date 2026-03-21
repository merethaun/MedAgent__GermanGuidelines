from typing import Optional

from app.constants.mongodb_config import (
    ANSWER_FEEDBACK_COLLECTION,
    EVALUATION_RUN_COLLECTION,
    EVALUATION_SAMPLE_COLLECTION,
    EVALUATOR_PROFILE_COLLECTION,
    MANUAL_REVIEW_TASK_COLLECTION,
    QUESTION_ENTRY_COLLECTION,
    QUESTION_GROUP_COLLECTION,
)
from app.services.auth.auth_service import AuthService
from app.services.backend_api_client import BackendApiClient
from app.services.evaluation.dataset_service import DatasetService
from app.services.evaluation.evaluator_profile_service import EvaluatorProfileService
from app.services.evaluation.feedback_service import FeedbackService
from app.services.evaluation.metric_service import MetricService
from app.services.evaluation.prompt_loader import PromptLoader
from app.services.evaluation.run_service import RunService
from app.services.evaluation.task_service import TaskService
from app.utils.mongo_collection_setup import get_collection, init_mongo

_auth_service: Optional[AuthService] = None
_backend_api_client: Optional[BackendApiClient] = None
_dataset_service: Optional[DatasetService] = None
_evaluator_profile_service: Optional[EvaluatorProfileService] = None
_task_service: Optional[TaskService] = None
_feedback_service: Optional[FeedbackService] = None
_metric_service: Optional[MetricService] = None
_run_service: Optional[RunService] = None


def init_services() -> None:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()

    init_mongo()

    global _backend_api_client
    if _backend_api_client is None:
        _backend_api_client = BackendApiClient()

    global _dataset_service
    if _dataset_service is None:
        _dataset_service = DatasetService(
            question_group_collection=get_collection(QUESTION_GROUP_COLLECTION),
            question_entry_collection=get_collection(QUESTION_ENTRY_COLLECTION),
            backend_client=_backend_api_client,
        )

    global _evaluator_profile_service
    if _evaluator_profile_service is None:
        _evaluator_profile_service = EvaluatorProfileService(get_collection(EVALUATOR_PROFILE_COLLECTION))

    global _task_service
    if _task_service is None:
        _task_service = TaskService(get_collection(MANUAL_REVIEW_TASK_COLLECTION))

    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackService(get_collection(ANSWER_FEEDBACK_COLLECTION), _backend_api_client)

    global _metric_service
    if _metric_service is None:
        _metric_service = MetricService(_backend_api_client, PromptLoader())

    global _run_service
    if _run_service is None:
        _run_service = RunService(
            run_collection=get_collection(EVALUATION_RUN_COLLECTION),
            sample_collection=get_collection(EVALUATION_SAMPLE_COLLECTION),
            dataset_service=_dataset_service,
            backend_client=_backend_api_client,
            metric_service=_metric_service,
            task_service=_task_service,
            feedback_service=_feedback_service,
        )


def reset_services() -> None:
    global _auth_service
    global _backend_api_client
    global _dataset_service
    global _evaluator_profile_service
    global _task_service
    global _feedback_service
    global _metric_service
    global _run_service

    _auth_service = None
    _backend_api_client = None
    _dataset_service = None
    _evaluator_profile_service = None
    _task_service = None
    _feedback_service = None
    _metric_service = None
    _run_service = None


def get_auth_service() -> AuthService:
    if _auth_service is None:
        init_services()
    return _auth_service


def get_dataset_service() -> DatasetService:
    if _dataset_service is None:
        init_services()
    return _dataset_service


def get_evaluator_profile_service() -> EvaluatorProfileService:
    if _evaluator_profile_service is None:
        init_services()
    return _evaluator_profile_service


def get_task_service() -> TaskService:
    if _task_service is None:
        init_services()
    return _task_service


def get_feedback_service() -> FeedbackService:
    if _feedback_service is None:
        init_services()
    return _feedback_service


def get_run_service() -> RunService:
    if _run_service is None:
        init_services()
    return _run_service
