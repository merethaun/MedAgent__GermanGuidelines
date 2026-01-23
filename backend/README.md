# BACKEND: MedAgent for German medical guidelines (simplified)

The backend contains the core application logic of **MedAgent**. It is responsible for
authentication, API endpoints, and later the integration of RAG workflows, databases,
and LLMs.

The backend is implemented using **FastAPI** and follows a clear
**Model–Service–Controller** architecture, inspired by:
https://medium.com/@jeremyalvax/fastapi-backend-architecture-model-controller-service-44e920567699

---

## Architectural principles

### Model layer

Defines data structures and schemas:

- request / response models
- internal domain models
- database schemas (added later)

### Service layer

Contains all business logic:

- authentication and token handling
- workflow execution logic
- interaction with external systems (LLMs, vector DBs, etc.)

Services should:

- be reusable
- not depend on FastAPI
- not import controllers
- avoid circular dependencies

### Controller layer

Defines the FastAPI routers and endpoints:

- validates and parses HTTP input
- delegates all logic to services
- formats HTTP responses and errors

Controllers should contain **minimal logic**.

---

## Project structure

```text
src/app/
├── models/        # Pydantic models, schemas, domain objects
│   ├── auth /
│   │   └── token.py, user.py
│   ├── common /                # including object id
│   └── knowledge /
│       └── guideline /
│           └── guideline_entry.py
├── services/      # Business logic (auth, workflows, evaluation, ...)
│   ├── service_registry.py     # collecting all services (singleton pattern)
│   ├── auth /
│   │   ├── auth_service.py     # validate user credentials
│   │   └── token_service.py    # create token
│   └── knowledge /
│       └── guideline /
│           └── guideline_service.py    # including pdf download
├── controllers/   # FastAPI routers / HTTP endpoints
│   ├── auth /                  # for getting auth tokens
│   ├── dependencies /          # for authentication (as dependency injected)
│   └── knowledge /
│       └── guideline /
│           └── guideline_router.py
├── utils/         # Shared helpers (logging, service factories, etc.)
├── constants/     # Centralized configuration (via environment variables)
│   ├── logging_config.py
│   ├── mongodb_config.py
│   └── auth_config.py
└── main.py        # FastAPI app setup and router registration
```

---

## Current scope

At the current stage, the backend provides:

- FastAPI application startup
- Swagger / OpenAPI documentation
- Keycloak-based authentication
- Role-based access control (`admin`, `study_user`)
- A development-only token endpoint (`/auth/token`)
- MongoDB interaction and PDF download for guideline entries

Full database integration, RAG pipelines, and evaluation logic will be added incrementally.

---

## Notes

- All configuration is provided via environment variables
- The backend is designed to run fully inside Docker
- Services are initialized once and injected via FastAPI dependencies
