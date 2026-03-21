from app.models.evaluation.dataset import QuestionClassification, QuestionEntry
from app.models.evaluation.run import EvaluationRunCreateRequest

ACCESS_TOKEN = "user-access-token"


def test_run_service_processes_question_group_batch_and_creates_task(run_service, current_user, seeded_question_group, seeded_question):
    run = run_service.create_run(
        EvaluationRunCreateRequest(
            name="batch-run",
            workflow_system_id="workflow-1",
            source_type="question_group_batch",
            question_group_id=str(seeded_question_group.id),
            manual_review_mode="open",
        ),
        current_user,
        ACCESS_TOKEN,
    )

    run_service.process_queued_runs_once()

    refreshed = run_service.get_run(str(run.id))
    samples = run_service.list_samples(run_id=str(run.id))

    assert refreshed.status == "completed"
    assert refreshed.total_samples == 1
    assert refreshed.open_tasks == 1
    assert samples[0].status == "completed"
    assert samples[0].automatic_metrics.lexical is not None
    assert samples[0].automatic_metrics.gpt_score is not None


def test_run_service_forwards_runtime_llm_settings_to_execution_and_gpt_score(
        run_service,
        current_user,
        seeded_question_group,
        seeded_question,
        fake_backend_client,
):
    run = run_service.create_run(
        EvaluationRunCreateRequest(
            name="batch-run-with-override",
            workflow_system_id="workflow-1",
            source_type="question_group_batch",
            question_group_id=str(seeded_question_group.id),
            manual_review_mode="none",
            runtime_llm_settings={
                "model": "openai/gpt-4.1-mini",
                "api_key": "secret",
                "base_url": "https://example.org/v1",
                "temperature": 0.1,
            },
        ),
        current_user,
        ACCESS_TOKEN,
    )

    run_service.process_queued_runs_once()

    assert run.id is not None
    assert fake_backend_client.last_runtime_llm_settings == {
        "model": "openai/gpt-4.1-mini",
        "api_key": "secret",
        "base_url": "https://example.org/v1",
        "temperature": 0.1,
        "extra_headers": {},
        "extra_body": {},
    }
    assert fake_backend_client.last_gpt_score_llm_settings == {
        "model": "openai/gpt-4.1-mini",
        "api_key": "secret",
        "base_url": "https://example.org/v1",
        "temperature": 0.1,
        "extra_headers": {},
        "extra_body": {},
    }
    assert fake_backend_client.last_access_token == ACCESS_TOKEN

    stored_doc = run_service.run_collection.find_one({"_id": run.id})
    assert stored_doc is not None
    assert "_run_access_token" not in stored_doc


def test_run_service_processes_chat_snapshot_without_lexical_metrics(run_service, current_user):
    run = run_service.create_run(
        EvaluationRunCreateRequest(
            name="chat-run",
            workflow_system_id="workflow-chat",
            source_type="chat_snapshot",
            source_chat_id="chat-existing",
            source_interaction_index=0,
            manual_review_mode="none",
        ),
        current_user,
        ACCESS_TOKEN,
    )

    run_service.process_queued_runs_once()

    sample = run_service.list_samples(run_id=str(run.id))[0]

    assert sample.status == "completed"
    assert sample.question_text == "What should I ask?"
    assert sample.automatic_metrics.lexical is None
    assert sample.automatic_metrics.retrieval is not None


def test_run_service_rerun_run_resets_samples_and_review_tasks(run_service, current_user, seeded_question_group, seeded_question):
    run = run_service.create_run(
        EvaluationRunCreateRequest(
            name="rerunnable-run",
            workflow_system_id="workflow-1",
            source_type="question_group_batch",
            question_group_id=str(seeded_question_group.id),
            manual_review_mode="open",
        ),
        current_user,
        ACCESS_TOKEN,
    )

    run_service.process_queued_runs_once()

    sample = run_service.list_samples(run_id=str(run.id))[0]
    assert sample.manual_review_task_id is not None
    assert run_service.task_service.collection.count_documents({"run_id": str(run.id)}) == 1

    queued_run = run_service.rerun_run(str(run.id), ACCESS_TOKEN)
    reset_sample = run_service.get_sample(str(sample.id))

    assert queued_run.status == "queued"
    assert queued_run.processed_samples == 0
    assert queued_run.failed_samples == 0
    assert queued_run.open_tasks == 0
    assert reset_sample.status == "queued"
    assert reset_sample.answer_text is None
    assert reset_sample.manual_review_task_id is None
    assert run_service.task_service.collection.count_documents({"run_id": str(run.id)}) == 0

    run_service.process_queued_runs_once()

    refreshed_run = run_service.get_run(str(run.id))
    rerun_sample = run_service.get_sample(str(sample.id))

    assert refreshed_run.status == "completed"
    assert refreshed_run.processed_samples == 1
    assert refreshed_run.open_tasks == 1
    assert rerun_sample.status == "completed"
    assert rerun_sample.manual_review_task_id is not None
    assert run_service.task_service.collection.count_documents({"run_id": str(run.id)}) == 1


def test_run_service_rerun_sample_only_requeues_selected_sample(
        run_service,
        current_user,
        seeded_question_group,
        seeded_question,
        dataset_service,
):
    dataset_service.create_question(
        QuestionEntry(
            question_group_id=seeded_question_group.id,
            question="What is the postoperative recommendation?",
            classification=QuestionClassification(super_class="Simple", sub_class="Text"),
            correct_answer="Provide the standard postoperative recommendation.",
            expected_retrieval=[],
        ),
    )

    run = run_service.create_run(
        EvaluationRunCreateRequest(
            name="partial-rerun",
            workflow_system_id="workflow-1",
            source_type="question_group_batch",
            question_group_id=str(seeded_question_group.id),
            manual_review_mode="open",
        ),
        current_user,
        ACCESS_TOKEN,
    )

    run_service.process_queued_runs_once()

    samples = run_service.list_samples(run_id=str(run.id))
    target_sample = samples[0]
    untouched_sample = samples[1]

    rerun_sample = run_service.rerun_sample(str(target_sample.id), ACCESS_TOKEN)
    queued_run = run_service.get_run(str(run.id))
    refreshed_samples = {str(sample.id): sample for sample in run_service.list_samples(run_id=str(run.id))}

    assert rerun_sample.status == "queued"
    assert queued_run.status == "queued"
    assert queued_run.processed_samples == 1
    assert queued_run.open_tasks == 1
    assert refreshed_samples[str(target_sample.id)].manual_review_task_id is None
    assert refreshed_samples[str(untouched_sample.id)].status == "completed"
    assert refreshed_samples[str(untouched_sample.id)].manual_review_task_id is not None
    assert run_service.task_service.collection.count_documents({"run_id": str(run.id)}) == 1

    run_service.process_queued_runs_once()

    completed_run = run_service.get_run(str(run.id))
    completed_samples = {str(sample.id): sample for sample in run_service.list_samples(run_id=str(run.id))}

    assert completed_run.status == "completed"
    assert completed_run.processed_samples == 2
    assert completed_run.open_tasks == 2
    assert completed_samples[str(target_sample.id)].status == "completed"
    assert completed_samples[str(target_sample.id)].manual_review_task_id is not None
