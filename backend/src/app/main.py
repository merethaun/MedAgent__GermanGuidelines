from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# noinspection PyUnresolvedReferences
import app.services.system.component_registry  ## MUST BE KEPT HERE!!
from app.routers.chat.chat_router import chat_router
from app.routers.guideline_evaluation.evaluation_results import generated_results_router
from app.routers.guideline_evaluation.question_dataset import question_dataset_router
from app.routers.knowledge.guidelines import guideline_router, references_router, keyword_router
from app.routers.knowledge.vector import vector_database_router, advanced_database_router
from app.routers.system.workflow_system_router import workflow_system_router
from app.utils.automatic_evaluators import get_rouge, get_bleu, get_meteor, get_bertscore
from app.utils.request_call import install_requests_cache_if_enabled, http_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    get_rouge();
    get_bleu();
    get_meteor();
    get_bertscore()
    install_requests_cache_if_enabled()
    _ = http_session()  # optional warm-up so TLS store/pool is ready
    try:
        yield
    finally:
        # --- shutdown ---
        try:
            http_session().close()  # optional: close pooled connections
        except Exception:
            pass


fast_app = FastAPI(
    title="MedAgent Guideline Backend", version="0.1.0",
    description="Provides interaction with knowledge bases, workflow system (creation + chat), and evaluation of generated answers.",
    lifespan=lifespan,
)

# Allow cross-origin requests so that the frontend can access the API from a different port
fast_app.add_middleware(
    CORSMiddleware, allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# Register file management routes
fast_app.include_router(references_router, prefix="/api/knowledge/guidelines/references", tags=["GuidelineReferences"])
fast_app.include_router(guideline_router, prefix="/api/knowledge/guidelines", tags=["Guidelines"])
fast_app.include_router(keyword_router, prefix="/api/knowledge/keywords", tags=["Keywords"])
fast_app.include_router(vector_database_router, prefix="/api/knowledge/vector", tags=["VectorDatabase"])
fast_app.include_router(advanced_database_router, prefix="/api/knowledge/advanced_db", tags=["AdvancedDatabaseInteraction"])
fast_app.include_router(workflow_system_router, prefix="/api/system/workflow_system", tags=["WorkflowSystem"])
fast_app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])

fast_app.include_router(
    question_dataset_router, prefix="/api/guideline_evaluation/question_dataset", tags=["GuidelineQuestionDataset"],
)
fast_app.include_router(
    generated_results_router, prefix="/api/guideline_evaluation/generated_results", tags=["GeneratedResults"],
)

# Start the service: Run with `python app/main.py` or `uvicorn app.main:app --reload`
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run("app.main:fast_app", host="0.0.0.0", port=5000, reload=True)
