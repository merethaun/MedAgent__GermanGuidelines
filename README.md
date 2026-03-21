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

The local setup expects one realm and two clients:

1. realm: `medagent`
2. browser client: `medagent-frontend`
3. backend helper client: `medagent-backend`

### 1. Create the realm

- Realm name: `medagent`

This realm name must match:

- `VITE_KEYCLOAK_REALM=medagent` in the frontend container
- `KEYCLOAK_REALM=medagent` in the backend container
- `OIDC_ISSUER=http://keycloak:8080/realms/medagent` in backend and evaluation

### 2. Create the realm roles

Create these realm roles in `Realm roles`:

- `admin`: full backend and evaluation access
- `study_user`: normal app usage
- `evaluator`: manual review and evaluation-task access

Use realm roles here, not client roles. The backend and evaluation services read roles from the token's `realm_access.roles`.

### 3. Create the clients

#### Frontend client: `medagent-frontend`

This is the browser SPA client used by the React frontend.

Recommended values:

- Client ID: `medagent-frontend`
- Client type: `OpenID Connect`
- Client authentication: `Off`
- Standard flow: `On`
- Direct access grants: `Off`
- Service accounts roles: `Off`
- Root URL: `http://localhost:5173`
- Home URL: `http://localhost:5173`
- Valid redirect URIs: `http://localhost:5173/*`
- Valid post logout redirect URIs: `http://localhost:5173/*`
- Web origins: `http://localhost:5173`

This must match `VITE_KEYCLOAK_CLIENT_ID=medagent-frontend` in `docker/docker-compose.yml`.

#### Backend client: `medagent-backend`

This client is not used as a browser app. It is mainly referenced by backend configuration and by the backend `/auth/token` helper, which requests a token via password grant for development/testing.

Recommended values:

- Client ID: `medagent-backend`
- Client type: `OpenID Connect`
- Client authentication: `Off`
- Standard flow: `Off`
- Direct access grants: `On`
- Service accounts roles: `Off`
- Root URL: leave empty
- Home URL: leave empty
- Valid redirect URIs: leave empty
- Valid post logout redirect URIs: leave empty
- Web origins: leave empty

The `http://localhost:3000` Root URL sometimes seen on this client is not needed for this repository. It looks like a stale leftover from another frontend setup and can be removed.

This client ID must match `KEYCLOAK_CLIENT_ID=medagent-backend` in `docker/docker-compose.yml`.

#### Evaluation access model

The evaluation frontend and backend now reuse the logged-in user's bearer token when the evaluation service calls the backend. That means there is no separate `medagent-evaluation` service-account client to configure for normal evaluation runs.

What this means in practice:

- if a user opens `/admin/evaluation`, their Keycloak login must already have the backend permissions needed for the actions triggered there
- for evaluation administration, assigning the realm role `admin` is the simplest setup because backend workflow access, guideline lookup, embeddings, and related tools are admin-protected
- for manual review only, `evaluator` is enough for `/evaluation/tasks`, but those users cannot create admin evaluation runs unless they also have `admin`

Because the evaluation worker is asynchronous, it temporarily stores the creator's access token with the queued run and removes it again once the run reaches a final state. A long-running run can still fail if that user token expires before processing finishes.

### 4. Add users and assign roles

To create a user:

1. open `Users`
2. create the user
3. set a password in `Credentials`
4. open `Role mapping`
5. assign one or more realm roles

Typical user role assignments:

- normal app user: `study_user`
- evaluator: `study_user` and `evaluator`
- administrator: `admin`

If you want to add an evaluator specifically, assign both `study_user` and `evaluator`. `study_user` allows normal app usage, while `evaluator` unlocks the evaluation review pages.

### 5. Values That Must Match

These values need to be filled in consistently between Keycloak and your Docker env file:

- realm name: `medagent`
- frontend client ID: `medagent-frontend`
- backend client ID: `medagent-backend`
- Keycloak admin username: set `KEYCLOAK_ADMIN_USER`
- Keycloak admin password: set `KEYCLOAK_ADMIN_PASSWORD`
- Keycloak database password: set `KEYCLOAK_DB_PASSWORD`

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
