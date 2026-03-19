# MedAgent for German Medical Guidelines (Simplified)

> Goal: a configurable RAG framework for German medical guidelines, especially AWMF-style guideline content.

This repository is a simplified reconstruction of the original master's thesis project. It already includes a backend for workflow-based retrieval and generation, a lightweight frontend scaffold, and a local Docker setup with authentication and supporting services.

## Repository Overview

The repository is organized into three main parts:

- `backend`: FastAPI backend for guideline storage, retrieval-source preparation, vector and graph infrastructure, workflows, chats, and tool testing
- `frontend`: React SPA scaffold with login and placeholder workflow/chat views
- `docker`: local development setup for backend, frontend, Keycloak, and related services

## Quick Start

### 1. Configure environment variables

```bash
cd docker
cp local.env .env
```

Fill the remaining `TODO` values in `.env`.

### 2. Start the local stack

```bash
cd docker
docker compose -p medagent --env-file .env up -d --build
```

### 3. Verify the main services

- Backend Swagger UI: `http://localhost:5000/docs`
- Keycloak Admin UI: `http://localhost:8080/admin`
- Frontend: `http://localhost:5173`

## Backend Documentation

The backend is best explored through Swagger UI for exact request and response shapes. The detailed backend architecture and workflow documentation lives in [`backend/README.md`](./backend/README.md).

That backend README covers:

- the current backend structure
- workflow component variants
- query transformers, retrievers, graph retrieval, filters, expanders, and prompt storage
- the full setup path from guideline references to vector and graph retrieval sources

## Frontend Scope

The frontend is still intentionally lightweight:

- `/login`: login and logout via Keycloak
- `/chats`: placeholder chat overview
- `/chat/:chatId`: placeholder chat detail view

## Backend Runtime Modes

The backend container supports two run modes via `MODE`:

- `MODE=update`: development mode with reload
- `MODE=build`: production-like mode without reload

## Keycloak Setup

Open Keycloak Admin UI at `http://localhost:8080/admin` and log in with `KEYCLOAK_ADMIN_USER` and `KEYCLOAK_ADMIN_PASSWORD`.

Recommended baseline setup:

1. create or select the `medagent` realm
2. ensure the roles `admin` and `study_user` exist
3. create the frontend client `medagent-frontend` as a public OpenID Connect client with PKCE
4. configure it for `http://localhost:5173`

Useful frontend client values:

- Root URL: `http://localhost:5173`
- Home URL: `http://localhost:5173`
- Valid redirect URIs: `http://localhost:5173/*`
- Valid post logout redirect URIs: `http://localhost:5173/*`
- Web origins: `http://localhost:5173`

## Persistence

Keycloak data is persisted under:

```text
./docker/data/keycloak
```

As long as that folder remains, users, roles, and realm configuration survive container restarts.

## SNOMED Note

SNOMED support is optional but available. Once the SNOMED data and licensing requirements are in place, the Swagger tool section is the easiest place to verify that the configured SNOMED helper setup works.

## What Comes Next

The next useful work areas are:

- smoother ingestion from PDFs into structured reference groups
- broader evaluation and benchmarking of workflow variants
- stronger frontend support for workflow authoring and retrieval-source management
