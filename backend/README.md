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
| `retriever/vector_retriever` | [`VectorRetriever`](./src/app/services/system/components/retriever/vector_retriever.py) | Queries a Weaviate collection during workflow execution and returns workflow-native retrieval references. Search settings are validated through [`VectorRetrieverSettings`](./src/app/models/system/workflow_retriever.py). |
| `retriever/multi_queries_vector_retriever` | [`MultiQueriesVectorRetriever`](./src/app/services/system/components/retriever/vector_retriever.py) | Executes multiple weighted Weaviate searches, merges duplicate hits, and returns the combined retrieval references. Settings are validated through [`MultiQueryVectorRetrieverSettings`](./src/app/models/system/workflow_retriever.py). |

### Example workflow

Create a workflow by posting a JSON object to POST `<backend>/system/workflow` that looks like:

- [Generator-only workflow](./tests/assets/example_gen_workflow.json) (! need to configure LLM settings)
- [Vector retrieval + generator workflow](./tests/assets/example_vector_retriever_workflow.json) (! need to configure LLM settings and ensure the Weaviate collection exists)
- [Multi-query vector retrieval + generator workflow](./tests/assets/example_multi_queries_vector_retriever_workflow.json) (! need to configure LLM settings and ensure the Weaviate collection exists)
- [Multi-query vector retrieval + prompt-store generator workflow](./tests/assets/example_multi_queries_vector_retriever_prompt_store_workflow.json) (! need to configure LLM settings and ensure the Weaviate collection exists)

### Retriever component notes

The workflow retriever abstraction now exposes one primary output:

- `component_id.references`: list of retrieval references compatible with `RetrievalResult`

The vector retriever additionally stores `component_id.latency`, so the `end` component can forward retrieval latency via `retrieval_latency_key`.

`retriever/vector_retriever` expects:

- `query`: template resolved against workflow data
- `settings`: object validated by `VectorRetrieverSettings`

Minimal settings shape:

```json
{
  "weaviate_collection": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
  "vector_name": "text",
  "limit": 5,
  "mode": "vector",
  "content_property": "text",
  "reference_id_property": "reference_id",
  "source_id_property": "guideline_id"
}
```

### Prompt store workflow example

Stored prompts now use typed prompt definitions with:

- `system_prompt`: the reusable instruction block
- `prompt`: an example prompt or default prompt template stored alongside the system prompt

The recommended pattern is to keep the reusable instruction in the prompt store and define the actual execution prompt directly in the generator component. That keeps the retrieval-to-prompt mapping adjustable per workflow.

Example:

```json
{
  "name": "Multi Query Vector Retrieval + Prompt Store Generator",
  "nodes": [
    {
      "component_id": "start",
      "name": "Start node",
      "type": "start",
      "parameters": {}
    },
    {
      "component_id": "retriever",
      "name": "Guideline multi-query vector retriever",
      "type": "retriever/multi_queries_vector_retriever",
      "parameters": {
        "settings": {
          "weaviate_collection": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
          "limit": 5,
          "per_query_limit": 8,
          "queries": [
            {
              "query": "{start.current_user_input}",
              "vector_name": "text",
              "weight": 1.0,
              "mode": "vector"
            },
            {
              "query": "{start.current_user_input}",
              "vector_name": "headers",
              "weight": 0.4,
              "mode": "vector"
            },
            {
              "mode": "hybrid",
              "keyword_properties": [
                "text",
                "headers"
              ],
              "alpha": 0.2
            }
          ],
          "content_property": "text",
          "reference_id_property": "reference_id",
          "source_id_property": "guideline_id"
        }
      }
    },
    {
      "component_id": "generator",
      "name": "OpenAI Generator",
      "type": "generator",
      "parameters": {
        "prompt_key": "awmf_clinical_qa_html_v1",
        "prompt": "{\ncontexts = []\nfor i, ref in enumerate(retriever.references):\n    properties = ref.weaviate_properties or {}\n    section = properties.get('headers', '')\n    text = properties.get('text') or ref.retrieval or ''\n    contexts.append(f'''<context_item id=\"{i}\" section=\"{section}\">\\n{text}\\n</context_item>''')\nreturn f'''<context>{chr(10).join(contexts)}</context>\\n<question>{start.current_user_input}</question>'''\n}",
        "llm_settings": {
          "model": "gpt-4o-mini",
          "api_key": "TODO",
          "base_url": "https://api.openai.com/v1",
          "max_tokens": 512,
          "timeout_s": 60
        }
      }
    },
    {
      "component_id": "end",
      "name": "End node",
      "type": "end",
      "parameters": {
        "generation_key": "{generator.response}",
        "retrieval_key": "{retriever.references}",
        "retrieval_latency_key": "{retriever.latency}"
      }
    }
  ],
  "edges": [
    {
      "source": "start",
      "target": "retriever"
    },
    {
      "source": "retriever",
      "target": "generator"
    },
    {
      "source": "generator",
      "target": "end"
    }
  ]
}
```

Here, `prompt_key` contributes the reusable AWMF system prompt, while `prompt` is defined in the workflow and can map whatever retrieval structure that workflow exposes.

`retriever/multi_queries_vector_retriever` expects:

- `settings`: object validated by `MultiQueryVectorRetrieverSettings`
- `settings.queries`: list of weighted query definitions, each with `query`, `vector_name`, and optional hybrid-search knobs

Minimal settings shape:

```json
{
  "weaviate_collection": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
  "limit": 5,
  "per_query_limit": 8,
  "queries": [
    {
      "query": "{start.current_user_input}",
      "vector_name": "text",
      "weight": 1.0
    },
    {
      "query": "{start.current_user_input}",
      "vector_name": "headers",
      "weight": 0.4
    }
  ],
  "content_property": "text",
  "reference_id_property": "reference_id",
  "source_id_property": "guideline_id"
}
```

---

### Example guideline to retrieval source

Via the backend API, add a guideline entry to the database.

Then, guideline references can be created in the frontend when they are assigned the role of `admin`.
Once logged in, a new tab with the name "reference management" will appear in the navigation bar.
Here, a new reference group can be created, and a guideline can be selected, allowing to now manage and add new references.
How to create a new one: currently only implemented with the bounding box text search.

If the retrieval source should work on chunks instead of the original references, create a second reference group as a
chunking result. Chunking only splits narrative text references; all other reference types stay as they are. The new
chunks get their own bounding boxes again, restricted to the page span of the original reference.

Available chunking strategies:

- `fixed_characters`
- `sentence`
- `paragraph`

Typical setup:

1. create a structured reference group for the guideline
2. create a chunking-result reference group from it, for example with `fixed_characters` and size `500`
3. use that chunking-result reference group as the basis for the vector collection

For the vector setup, see [example_vector_collection_ref_spec.json](./tests/assets/example_vector_collection_ref_spec.json).
That example is shaped for the collection-creation endpoint and includes the ingestion mapping used by the related reference-group ingestion endpoint.

- TODOs are to include the actual reference group ID
- And also: remove the `_related_ingest_reference_group_request_example`, this is for when actually filling the vector database

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
    - SNOMED CT lookup helpers (synonyms, canonical form, keyword expansion, medical keyword extraction)
    - LLM interaction sessions (create session with LLM settings, chat continuation via session id, history/reset)
    - Deletion functions and creation / update for workflows, guidelines, and references
    - Keyword enrichment for stored references / reference groups
    - Reference-group chunking for retrieval-source preparation
- Admin-only vector endpoints for:
    - Embedding via registered vectorizers
    - Creating Weaviate manual-vector collections
    - Inserting and searching vector objects

Full database integration, RAG pipelines, and evaluation logic will be added incrementally.

---

## Notes

- All configuration is provided via environment variables
- The backend is designed to run fully inside Docker
- Services are initialized once and injected via FastAPI dependencies

## Vector services

Two new backend services are available under the `knowledge/vector` slice:

- `EmbeddingService`: provider-backed text embeddings
- `WeaviateVectorStoreService`: Weaviate collection setup, insert, and search with stored metadata in MongoDB

An example collection setup is available in [example_vector_collection_ref_spec.json](./tests/assets/example_vector_collection_ref_spec.json).
It assumes that the chunking-result reference group already exists, for example a `fixed_characters` chunking with size `500`.
Whole-group ingestion creates chunk indices per guideline automatically. The ingest request can optionally target one guideline only, and guideline-level replacement always restarts chunk indices at `0`.

For workflow orchestration, the matching ready-to-use workflow example is [example_vector_retriever_workflow.json](./tests/assets/example_vector_retriever_workflow.json).
It is configured against the Weaviate collection `OpenSource_StructuredGuidelineFixedCharacters500_RefSpec`.
For multiple weighted searches against the same collection, see [example_multi_queries_vector_retriever_workflow.json](./tests/assets/example_multi_queries_vector_retriever_workflow.json).

## SNOMED tool endpoints

The backend now exposes a separate SNOMED tool router under `/tools/snomed/*`:

- `POST /tools/snomed/versions`
- `POST /tools/snomed/synonyms`
- `POST /tools/snomed/canonical`
- `POST /tools/snomed/expand`
- `POST /tools/snomed/medical-keywords`

Each SNOMED request carries its own `llm_settings` in the JSON body. This is required because translation fallback and medical-keyword extraction run through the configured LLM for that specific request.

The SNOMED instance can also be configured per request through `snomed_settings`, but useful defaults are now built in:

- `base_url`: `http://snomed-lite:8080/fhir`
- `version`: `http://snomed.info/sct/11000274103/version/20250515`
- `display_language_de`: `de`
- `display_language_en`: `en`

These defaults can be overridden via environment variables such as `SNOMED_BASE_URL`, or per request when needed.

Minimal example:

```json
{
  "term": "Blinddarmentzündung",
  "llm_settings": {
    "model": "gpt-4.1-mini",
    "api_key": "..."
  },
  "snomed_settings": {
    "base_url": "http://snomed-lite:8080/fhir"
  }
}
```

If you use the defaults, you can omit `snomed_settings` entirely and send only `term` plus `llm_settings`.

`POST /tools/snomed/versions` is useful for checking which SNOMED versions the configured server currently exposes. It first tries the FHIR `CodeSystem` endpoint and falls back to `/metadata` if necessary.

## Reference keyword enrichment

The backend exposes two keyword-enrichment endpoints that write extracted keywords into `associated_keywords`:

- `POST /guideline_references/{reference_id}/keywords`
- `POST /guideline_references/groups/{reference_group_id}/keywords`

The group endpoint can optionally be restricted to a single `guideline_id`.

Extraction supports YAKE or LLM settings, and the extracted keywords can optionally be expanded via SNOMED before being stored.
