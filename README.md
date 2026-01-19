# MedAgent for German medical guidelines (simplified)

> **Goal:** Framework for configurable RAG workflows grounded in German medical guidelines (e.g., AWMF).

This repository represents a **step-by-step reconstruction** of the original master’s thesis project.
The setup is intentionally minimal (not full repo) and evolves incrementally.

---

## Current state (backend + authentication)

At this stage, the stack contains:

- **Backend (FastAPI)** – runnable via Docker
- **Authentication (Keycloak)** – user management and role-based access control

Not included yet:

- frontend
- databases (MongoDB, Weaviate, etc.)
- model caching or preprocessing pipelines

---

## Quick start

### 1) Configure environment variables

Copy `local.env` to `.env` and fill all `TODO` values:

```bash
cd docker
cp local.env .env
# edit .env
```

---

### 2) Start backend + Keycloak

```bash
docker compose -p medagent --env-file .env up -d --build
```

---

### 3) Verify services

- Backend Swagger UI: http://localhost:5000/docs
- Keycloak Admin UI: http://localhost:8080/admin

---

## Runtime behavior (backend)

The backend Docker image supports **two run modes**, controlled via the environment variable `MODE`:

### MODE=update

- Development mode
- FastAPI runs with `--reload`
- Code changes are picked up automatically

### MODE=build

- Production-like mode
- Multiple Uvicorn workers
- No auto-reload

The mode is configured once when the container is started.

---

## Exposed services

- **FastAPI backend:** http://localhost:5000
    - Swagger UI: http://localhost:5000/docs
- **Keycloak Admin UI:** http://localhost:8080/admin

---

## Keycloak persistence

Keycloak stores all realm configuration, users, and roles in Postgres.
In this project, the database is persisted on the host:

```text
./docker/data/keycloak
```

As long as this folder exists, all users and settings survive container restarts.

---

## How to add a new user (Keycloak)

1) Open Keycloak Admin UI  
   http://localhost:8080/admin  
   Log in using `KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD`.

2) Select (or create) the realm **medagent**

3) Ensure realm roles exist:
    - `admin`
    - `study_user`

4) Create a user:
    - **Users** → **Add user**
    - Set **Username** → **Create**

5) Set password:
    - **Credentials** → **Set password**
    - Set **Temporary = OFF**

6) Assign role:
    - **Role mapping**
    - Assign either `admin` or `study_user`

User maintenance (password reset, role changes, disabling users) is handled entirely in Keycloak.

---

## Backend documentation

For backend architecture and implementation details, see [`backend/README.md`](./backend/README.md)

---

## What comes next

Planned next steps:

- MongoDB and Weaviate integration
- RAG workflow execution
- guideline ingestion pipelines
- minimal React-based frontend
- evaluation and benchmarking components
