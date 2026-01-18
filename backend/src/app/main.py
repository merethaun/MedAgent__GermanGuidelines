from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

fast_app = FastAPI(
    title="MedAgent Guideline Backend", version="0.1.0",
    description="Provides interaction with knowledge bases, workflow system (creation + chat), and evaluation of generated answers.",
)

# Allow cross-origin requests so that the frontend can access the API from a different port
fast_app.add_middleware(
    CORSMiddleware, allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run("app.main:fast_app", host="0.0.0.0", port=5000, reload=True)
