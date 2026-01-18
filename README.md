# MedAgent for German medical guidelines (simplified)

> **Goal:** Framework for configurable RAG workflows grounded in German medical guidelines (e.g., AWMF).

This repository represents a **step-by-step reconstruction** of the original master’s thesis project.
The setup is intentionally minimal and evolves incrementally.

---

## Current state (backend-only)

At this stage, **only the backend (FastAPI)** is included and runnable.

- No frontend
- No authentication
- No databases (MongoDB, Weaviate, etc.)
- No model caching or preprocessing pipelines

The backend can already:

- start a FastAPI application
- expose API endpoints for further development
- serve as the foundation for later extensions (auth, data stores, RAG pipelines)

---

## Runtime behavior

The backend Docker image supports **two run modes**, controlled via the environment variable `MODE`:

- `MODE=update`
    - Development mode
    - Starts FastAPI with `--reload`
    - Code changes are picked up automatically

- `MODE=build`
    - Production-like mode
    - Starts FastAPI with multiple workers
    - No auto-reload

The mode is configured **once** when the container is started.

---

## Exposed service

- **FastAPI backend:** http://localhost:5000
- Swagger UI: http://localhost:5000/docs

---

## Backend documentation

For backend-specific architecture and structure details, see: [`backend/README.md`](backend/README.md)

## What comes next

Future steps will gradually add:

- persistent datastores (MongoDB, Weaviate)
- authentication and role-based access (Keycloak)
- a minimal React-based frontend
- configurable RAG workflows and guideline ingestion

