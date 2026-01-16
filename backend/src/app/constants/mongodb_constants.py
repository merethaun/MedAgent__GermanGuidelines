import os

# MongoDB connection settings
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")  # fallback for local development
MONGODB_DATABASE = "medagent"  # "normal" system interaction database

# MongoDB collection names inside the "normal" system interaction database
GUIDELINE_COLLECTION = "guidelines"
GUIDELINE_REFERENCE_GROUPS_COLLECTION = "guideline_reference_groups"
GUIDELINE_REFERENCE_COLLECTION = "guideline_references"
VECTOR_DATABASES_COLLECTION = "vector_dbs"
WORKFLOW_SYSTEMS_COLLECTION = "workflow_systems"
CHATS_COLLECTION = "chats"

# guideline PDFs folder location
GUIDELINE_PDFS_FOLDER = "/data/guidelines/pdfs"  # fallback
WEAVIATE_HIERARCHY_INDEX_FOLDER = "/hierarchy_index_data"

EVAL_MONGODB_DATABASE = os.getenv("MEDAGENT_EVALUATION_DB", "eval__medagent")  # evaluation database

# MongoDB collection names inside the evaluation database
QUESTION_DS_GROUP_COLLECTION = "dataset_group"
QUESTION_DS_COLLECTION = "question_answers"
GENERATED_RESULTS_COLLECTION = "generated_results"
EVALUATORS_COLLECTION = "manual_evaluators"
