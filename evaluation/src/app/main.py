from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import dataset_router, evaluator_router, feedback_router, run_router, task_router
from app.services.service_registry import get_run_service, init_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_services()
    run_service = get_run_service()
    run_service.start_worker()
    yield
    await run_service.stop_worker()


main_app = FastAPI(
    title="MedAgent Evaluation Service",
    version="0.1.0",
    description="Dedicated evaluation API for datasets, runs, samples, manual review, and answer feedback.",
    lifespan=lifespan,
)

main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

main_app.include_router(dataset_router, prefix="/evaluation", tags=["EvaluationDatasets"])
main_app.include_router(run_router, prefix="/evaluation", tags=["EvaluationRuns"])
main_app.include_router(task_router, prefix="/evaluation", tags=["EvaluationTasks"])
main_app.include_router(feedback_router, prefix="/evaluation", tags=["EvaluationFeedback"])
main_app.include_router(evaluator_router, prefix="/evaluation", tags=["EvaluationEvaluators"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:main_app", host="0.0.0.0", port=5001, reload=True)
