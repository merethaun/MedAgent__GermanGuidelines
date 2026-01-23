import os

MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "medagent")

GUIDELINE_PDF_FOLDER = os.getenv("GUIDELINE_PDF_FOLDER", "pdfs")

# MongoDB collection names
GUIDELINE_COLLECTION = "guidelines"
