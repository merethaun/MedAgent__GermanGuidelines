import os

MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "medagent")

GUIDELINE_PDF_FOLDER = os.getenv("GUIDELINE_PDF_FOLDER", "pdfs")

# MongoDB collection names
GUIDELINE_COLLECTION = "guidelines"
GUIDELINE_REFERENCE_COLLECTION = "guideline_references"
GUIDELINE_REFERENCE_GROUP_COLLECTION = "guideline_reference_groups"
WORKFLOW_SYSTEM_COLLECTION = "workflow_systems"
CHAT_COLLECTION = "chats"
