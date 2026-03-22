import pytest
from bson import ObjectId

from app.models.evaluation.run import EvaluationRun
from app.models.evaluation.task import ManualReviewSubmission


def test_task_claim_and_submit_flow(task_service, current_user):
    task = task_service.create_for_sample(
        run=EvaluationRun(
            _id=ObjectId(),
            name="run",
            workflow_system_id="workflow-1",
            source_type="chat_snapshot",
            created_by_sub="creator",
        ),
        sample=type("SampleLike", (), {"id": ObjectId("507f1f77bcf86cd799439012")})(),
        assignment_mode="open",
        assigned_evaluator_sub=None,
        assigned_evaluator_username=None,
    )

    claimed = task_service.claim_task(str(task.id), current_user)
    completed = task_service.submit_task(
        str(claimed.id),
        current_user,
        ManualReviewSubmission(correctness_score=4, fact_count_overall=3, fact_count_backed=2),
    )

    assert claimed.status == "claimed"
    assert completed.status == "completed"
    assert completed.review is not None
    assert completed.review.factuality_ratio == 2 / 3


def test_task_cannot_be_claimed_twice(task_service, current_user):
    task = task_service.create_for_sample(
        run=EvaluationRun(
            _id=ObjectId(),
            name="run",
            workflow_system_id="workflow-1",
            source_type="chat_snapshot",
            created_by_sub="creator",
        ),
        sample=type("SampleLike", (), {"id": ObjectId("507f1f77bcf86cd799439013")})(),
        assignment_mode="open",
        assigned_evaluator_sub=None,
        assigned_evaluator_username=None,
    )

    task_service.claim_task(str(task.id), current_user)

    with pytest.raises(ValueError, match="not available to claim"):
        task_service.claim_task(str(task.id), current_user)
