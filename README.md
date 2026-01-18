# MedAgent for German medical guidelines (simplified)

> **Goal:** Framework for configurable RAG workflows grounded in German medical guidelines (e.g., AWMF).

This repository represents a **step-by-step reconstruction** of the original master’s thesis project.
The setup is intentionally minimal and evolves incrementally.

---

## Current state (backend + authentication)

At this stage, the stack contains:

- **Backend (FastAPI)** (runnable via Docker)
- **Authentication (Keycloak)** for user management and role-based access

Not included yet:

- no frontend
- no databases (MongoDB, Weaviate, etc.)
- no model caching or preprocessing pipelines

---

## Quick start

1) Set environment variables  
   Copy `local.env` to `.env` and fill the `TODO` values:

```bash
# inside ./docker/
cp local.env .env
# edit .env and replace TODO values
```

2) Start the stack (backend + Keycloak)

```bash
docker compose -p medagent --env-file .env up -d --build
```

3) Verify services

- Backend Swagger UI: http://localhost:5000/docs
- Keycloak Admin UI: http://localhost:8080/admin

## Runtime behavior (backend)

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

## Exposed services

- **FastAPI backend:** http://localhost:5000
    - Swagger UI: http://localhost:5000/docs

- **Keycloak Admin UI:** http://localhost:8080/admin

---

## Keycloak persistence

Keycloak stores users/roles/realm configuration in its Postgres database.  
In this project, the database is persisted as a **host folder**:

- `./data/keycloak` (relative to the `docker-compose.yml`)

As long as this folder remains, users and configuration persist across container restarts and `docker compose down`.

---

## How to add a new user (Keycloak)

1) Open Keycloak Admin UI: http://localhost:8080/admin  
   Log in with `KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD`.

2) Select (or setup) the realm `medagent` → dropdown on top left

3) Ensure realm roles exist:
    - `admin`
    - `study_user`

4) Create user:
    - **Users** → **Add user**
    - Set **Username** → **Create**

5) Set password:
    - **Credentials** → **Set password**
    - (Optional) set **Temporary = OFF** to avoid forced reset on first login

6) Assign role:
    - **Role mapping** → assign either `admin` or `user`

User maintenance (disable users, reset passwords, change roles) is done in the same Keycloak Admin UI.

---

## Backend documentation

For backend-specific architecture and structure details, see: [`backend/README.md`](backend/README.md)

---

## What comes next

Future steps will gradually add:

- persistent datastores (MongoDB, Weaviate)
- a minimal React-based frontend
- configurable RAG workflows and guideline ingestion
