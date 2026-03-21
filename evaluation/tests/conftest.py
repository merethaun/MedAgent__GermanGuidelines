from datetime import datetime, timezone
from typing import Any, Dict

import mongomock
import pytest

from app.models.auth.user import CurrentUser
from app.models.evaluation.dataset import QuestionClassification, QuestionEntry, QuestionGroup
from app.services.evaluation.dataset_service import DatasetService
from app.services.evaluation.evaluator_profile_service import EvaluatorProfileService
from app.services.evaluation.feedback_service import FeedbackService
from app.services.evaluation.metric_service import MetricService
from app.services.evaluation.prompt_loader import PromptLoader
from app.services.evaluation.run_service import RunService
from app.services.evaluation.task_service import TaskService


class FakeBackendClient:
    def __init__(self):
        self.chat_counter = 0
        self.last_runtime_llm_settings = None
        self.last_gpt_score_llm_settings = None
        self.last_access_token = None
        self.guidelines = [
            {
                "_id": "guideline-1",
                "awmf_register_number_full": "007-001",
                "title": "Guideline A",
                "download_information": {
                    "url": "https://example.org/guidelines/007-001.pdf",
                },
            },
            {
                "_id": "guideline-2",
                "awmf_register_number_full": "007-002",
                "title": "Guideline B",
                "download_information": {
                    "url": "https://example.org/guidelines/007-002.pdf",
                },
            },
        ]

    def list_guidelines(self, access_token: str):
        self.last_access_token = access_token
        return self.guidelines

    def get_workflow(self, workflow_id: str, access_token: str) -> Dict[str, Any]:
        self.last_access_token = access_token
        return {"_id": workflow_id, "name": f"Workflow {workflow_id}"}

    def create_chat(self, workflow_id: str, username: str, access_token: str, name: str | None = None) -> Dict[str, Any]:
        self.chat_counter += 1
        self.last_access_token = access_token
        return {"_id": f"chat-{self.chat_counter}", "workflow_system_id": workflow_id, "username": username, "name": name}

    def pose_question(self, chat_id: str, user_input: str, access_token: str, runtime_llm_settings=None) -> Dict[str, Any]:
        self.last_runtime_llm_settings = runtime_llm_settings
        self.last_access_token = access_token
        return {
            "_id": chat_id,
            "interactions": [
                {
                    "user_input": user_input,
                    "generator_output": "Expected answer with nerve relation.",
                    "time_question_input": datetime.now(timezone.utc).isoformat(),
                    "time_response_output": datetime.now(timezone.utc).isoformat(),
                    "retrieval_output": [{"retrieval": "Use 3D imaging when nerve relation is suspected."}],
                    "retrieval_latency": 0.4,
                    "workflow_execution": [{"component_id": "end", "execution_order": 1, "output": {"answer": "ok"}}],
                },
            ],
        }

    def get_chat(self, chat_id: str, access_token: str) -> Dict[str, Any]:
        self.last_access_token = access_token
        return {
            "_id": chat_id,
            "workflow_system_id": "workflow-chat",
            "interactions": [
                {
                    "user_input": "What should I ask?",
                    "generator_output": "A grounded answer",
                    "time_question_input": datetime.now(timezone.utc).isoformat(),
                    "time_response_output": datetime.now(timezone.utc).isoformat(),
                    "retrieval_output": [{"retrieval": "Reference snippet from the backend"}],
                    "retrieval_latency": 0.2,
                    "workflow_execution": [],
                },
            ],
        }

    def find_bounding_boxes(
            self,
            *,
            access_token: str,
            guideline_id: str,
            text: str,
            start_page: int | None = None,
            end_page: int | None = None,
    ):
        self.last_access_token = access_token
        return [
            {
                "page": start_page or 12,
                "positions": [10.0, 20.0, 30.0, 40.0],
            },
        ]

    def embed_texts(self, texts, access_token: str):
        self.last_access_token = access_token
        return {"provider": "fake", "embeddings": [[1.0, 0.0], [1.0, 0.0]]}

    def run_gpt_score(self, system_prompt: str, user_prompt: str, access_token: str, runtime_llm_settings=None) -> str:
        self.last_gpt_score_llm_settings = runtime_llm_settings
        self.last_access_token = access_token
        return '{"similarity": 5, "reasoning": "Strong semantic match."}'


@pytest.fixture
def fake_backend_client():
    return FakeBackendClient()


@pytest.fixture
def mongo_db():
    client = mongomock.MongoClient()
    return client["medagent_evaluation_test"]


@pytest.fixture
def dataset_service(mongo_db, fake_backend_client):
    return DatasetService(
        question_group_collection=mongo_db["question_groups"],
        question_entry_collection=mongo_db["question_entries"],
        backend_client=fake_backend_client,
    )


@pytest.fixture
def task_service(mongo_db):
    return TaskService(mongo_db["manual_review_tasks"])


@pytest.fixture
def feedback_service(mongo_db, fake_backend_client):
    return FeedbackService(mongo_db["answer_feedback"], fake_backend_client)


@pytest.fixture
def evaluator_profile_service(mongo_db):
    return EvaluatorProfileService(mongo_db["evaluator_profiles"])


@pytest.fixture
def metric_service(fake_backend_client):
    return MetricService(fake_backend_client, PromptLoader())


@pytest.fixture
def run_service(mongo_db, dataset_service, fake_backend_client, metric_service, task_service, feedback_service):
    return RunService(
        run_collection=mongo_db["evaluation_runs"],
        sample_collection=mongo_db["evaluation_samples"],
        dataset_service=dataset_service,
        backend_client=fake_backend_client,
        metric_service=metric_service,
        task_service=task_service,
        feedback_service=feedback_service,
    )


@pytest.fixture
def current_user():
    return CurrentUser(sub="user-1", username="alice", roles={"admin", "evaluator"})


@pytest.fixture
def seeded_question_group(dataset_service):
    return dataset_service.create_question_group(QuestionGroup(name="Core questions", description="for testing"))


@pytest.fixture
def seeded_question(dataset_service, seeded_question_group):
    return dataset_service.create_question(
        QuestionEntry(
            question_group_id=seeded_question_group.id,
            question="When should 3D imaging be used before extraction?",
            classification=QuestionClassification(super_class="Simple", sub_class="Recommendation"),
            correct_answer="Expected answer with nerve relation.",
            expected_retrieval=[
                {
                    "guideline_source": "https://example.org/guidelines/007-001.pdf",
                    "guideline_title": "Guideline A",
                    "bounding_boxes": [
                        {
                            "page": 17,
                            "positions": [1.0, 2.0, 3.0, 4.0],
                        },
                    ],
                    "reference_type": "text",
                    "retrieval_text": "Use 3D imaging when nerve relation is suspected.",
                },
            ],
            note="Clinical imaging",
        ),
    )
