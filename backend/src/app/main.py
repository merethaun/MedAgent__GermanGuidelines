from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import auth_router, test_router
from app.controllers.knowledge.guideline import guideline_router
from app.services.service_registry import init_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_services()
    yield


main_app = FastAPI(
    title="MedAgent Guideline Backend",
    version="0.1.0",
    description="Provides interaction with knowledge bases, workflow system (creation + chat), and evaluation of generated answers.",
    lifespan=lifespan,
)

# Allow cross-origin requests so that the frontend can access the API from a different port
main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

main_app.include_router(auth_router, prefix="/auth", tags=["Auth"])
main_app.include_router(test_router, prefix="/test", tags=["Test"])

# Knowledge setup
main_app.include_router(guideline_router, prefix="/guidelines", tags=["Guidelines"])

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run("app.main:main_app", host="0.0.0.0", port=5000, reload=True)
