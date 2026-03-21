import os

EVALUATION_MONGODB_URI = os.getenv("EVALUATION_MONGODB_URI", os.getenv("MONGODB_URI", ""))
EVALUATION_MONGODB_DB_NAME = os.getenv("EVALUATION_MONGODB_DB_NAME", "medagent_evaluation")

QUESTION_GROUP_COLLECTION = "question_groups"
QUESTION_ENTRY_COLLECTION = "question_entries"
EVALUATION_RUN_COLLECTION = "evaluation_runs"
EVALUATION_SAMPLE_COLLECTION = "evaluation_samples"
MANUAL_REVIEW_TASK_COLLECTION = "manual_review_tasks"
ANSWER_FEEDBACK_COLLECTION = "answer_feedback"
EVALUATOR_PROFILE_COLLECTION = "evaluator_profiles"
