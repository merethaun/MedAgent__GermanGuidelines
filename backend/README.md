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

### Exception layer (cross-cutting)

Defines domain-specific exceptions that can be raised from services and translated into
consistent HTTP errors in controllers.

---

## Project structure

```text
src/app/
├── constants/     # Centralized configuration (via environment variables)
│   ├── auth_config.py
│   ├── logging_constants.py
│   └── mongodb_config.py
├── controllers/   # FastAPI routers / HTTP endpoints
│   ├── auth /
│   │   ├── auth_router.py
│   │   └── __init__.py
│   ├── dependencies /
│   │   ├── auth_dependencies.py
│   │   └── __init__.py
│   ├── knowledge /
│   │   └── guideline /
│   │       ├── guideline_router.py
│   │       ├── guideline_reference_router.py
│   │       └── __init__.py
│   ├── system /
│   │   ├── system_router.py
│   │   └── __init__.py
│   └── tools /
│       ├── tools_test_router.py
│       └── __init__.py
├── exceptions/    # Domain-specific exceptions
│   ├── knowledge /
│   │   └── guideline /
│   │       ├── guideline_error.py
│   │       ├── guideline_reference_error.py
│   │       └── __init__.py
│   ├── system /
│   │   └── chat /
│   │       ├── chat_error.py
│   │       └── __init__.py
│   └── tools /
│       ├── llm_interaction_error.py
│       └── __init__.py
├── models/        # Pydantic models, schemas, domain objects
│   ├── auth /
│   │   ├── token.py
│   │   ├── user.py
│   │   └── __init__.py
│   ├── common /
│   │   ├── py_object_id.py
│   │   └── __init__.py
│   ├── knowledge /
│   │   └── guideline /
│   │       ├── guideline_entry.py
│   │       ├── guideline_reference.py
│   │       └── __init__.py
│   ├── system /
│   │   ├── system_chat_interaction.py
│   │   ├── workflow_system.py
│   │   └── __init__.py
│   └── tools /
│       ├── keyword_interaction.py
│       ├── llm_interaction.py
│       └── __init__.py
├── services/      # Business logic (auth, workflows, evaluation, ...)
│   ├── service_registry.py
│   ├── auth /
│   │   ├── auth_service.py
│   │   ├── token_service.py
│   │   └── __init__.py
│   ├── knowledge /
│   │   └── guideline /
│   │       ├── guideline_service.py              # incl. PDF download
│   │       ├── guideline_reference_service.py    # incl. reference groups
│   │       └── __init__.py
│   ├── system /
│   │   ├── workflow_system_interaction_service.py
│   │   ├── workflow_system_storage_service.py
│   │   ├── chat /
│   │   │   ├── chat_service.py
│   │   │   └── __init__.py
│   │   └── components /
│   │       ├── abstract_component.py
│   │       ├── component_registry.py
│   │       └── structure /
│   │           ├── start_component.py
│   │           ├── end_component.py
│   │           └── __init__.py
│   └── tools /
│       ├── keyword_service.py
│       ├── llm_interaction_service.py
│       └── __init__.py
├── utils/         # Shared helpers (logging, service factories, etc.)
│   ├── llm_client.py
│   ├── logging.py
│   ├── mongo_collection_setup.py
│   └── system /
│       ├── render_template.py
│       ├── resolve_component_path.py
│       └── __init__.py
└── main.py        # FastAPI app setup and router registration
```

### Available system workflow components

System workflows are built from **components**. All components inherit from
[`AbstractComponent`](src/app/services/system/components/abstract_component.py) and are registered via:

- `AbstractComponent.variants = {"start": StartComponent, "end": EndComponent ...}`

The currently available component variants are:

| Variant name | Component class                                                                       | Description / Purpose                                                                                                                                                                                               |
|--------------|---------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `start`      | [`StartComponent`](./src/app/services/system/components/structure/start_component.py) | Required as start to provide user input                                                                                                                                                                             |
| `end`        | [`EndComponent`](./src/app/services/system/components/structure/end_component.py)     | Required as end to define generator output (text) and retrieval result (references)                                                                                                                                 |
| `generator`  | [`LLMGenerator`](./src/app/services/system/components/generator/generator.py)         | Executes the actual text generation step by sending a resolved prompt to the configured LLM and returning the model response. The LLM is configured via [`LLMSettings`](./src/app/models/tools/llm_interaction.py). |

### Example workflow

Create a workflow by posting a JSON object to POST `<backend>/system/workflow` that looks like:

- [Generator-only workflow](./tests/assets/example_gen_workflow.json) (! need to configure LLM settings)

---

## Current scope

At the current stage, the backend provides:

- FastAPI application startup
- Swagger / OpenAPI documentation
- Keycloak-based authentication
- Role-based access control (`admin`, `study_user`)
- A development-only token endpoint (`/auth/token`)
- MongoDB interaction and PDF download for guideline entries
- A basic system/chat scaffolding (router + service + models) for the simplified setup
- Admin-only tool endpoints for:
    - Keyword extraction (YAKE, LLM, and comparison of both)
    - LLM interaction sessions (create session with LLM settings, chat continuation via session id, history/reset)
    - Deletion functions and creation / update for workflows, guidelines, and references

Full database integration, RAG pipelines, and evaluation logic will be added incrementally.

---

## Notes

- All configuration is provided via environment variables
- The backend is designed to run fully inside Docker
- Services are initialized once and injected via FastAPI dependencies
