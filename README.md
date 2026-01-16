# MedAgent for German medical guidelines (simplified)

> **Goal:** Framework for configurable RAG workflows grounded in German medical guidelines (e.g., AWMF).

This repository is a simplified version of the original framework.  
The current Docker setup contains:

1. **Backend** (FastAPI): create / run RAG workflows, interact via API
2. **Datastores**:
   * **MongoDB** (metadata, chats, configs, etc.)
   * **Weaviate** (vector DB)

> **Note:** Authentication service + frontend are not yet included in the current `docker-compose.yml`. These will be added later.

---

## Prerequisites

* Docker + Docker Compose (v2 recommended)
* Enough disk space for:
  * MongoDB data
  * Weaviate data
  * HuggingFace model cache (can be large)
  * guideline PDFs folder

---

## Configuration

Create an `.env` file (next to `docker-compose.yml`) and set the required environment variables.

### Required environment variables

#### Storage locations (host paths)

These must be **absolute paths** on the host.

```bash
# MongoDB / Weaviate persistence
MEDAGENT_MONGODB_DATA_DIR=/absolute/path/to/data/mongodb
MEDAGENT_WEAVIATE_DATA_DIR=/absolute/path/to/data/weaviate

# Guideline PDFs mounted into backend as /data
GUIDELINE_PDFS_FOLDER=/absolute/path/to/guideline_pdfs

# HuggingFace cache mounted into backend as /models-cache
MEDAGENT_HF_DATA_DIR=/absolute/path/to/cache/hf_models

# Hierarchical index storage (mounted into backend as /hierarchy_index_data)
HIERARCHICAL_WEAVIATE_INDEX_LOCATION=/absolute/path/to/data/hierarchy_index
````

#### Credentials / secrets

```bash
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_BASE=...
OPEN_AI_TYPE=...                  # e.g. "azure" / whatever your backend expects
WARHOL_OLLAMA_API_BASE=...         # optional depending on setup
MEDAGENT_EVALUATION_DB=...         # backend-specific (db name or connection string)
```

---

## Folder setup

Create all directories referenced in the `.env`:

```bash
mkdir -p \
  "$MEDAGENT_MONGODB_DATA_DIR" \
  "$MEDAGENT_WEAVIATE_DATA_DIR" \
  "$GUIDELINE_PDFS_FOLDER" \
  "$MEDAGENT_HF_DATA_DIR" \
  "$HIERARCHICAL_WEAVIATE_INDEX_LOCATION"
```

Make sure Docker has read/write permissions for these folders (especially on servers).

---

## Start the stack

From the folder containing `docker-compose.yml`:

```bash
docker compose -p medagent --env-file .env up -d --build
```

To see logs:

```bash
docker compose -p medagent logs -f
```

To stop:

```bash
docker compose -p medagent down
```

To stop **and remove containers** (data remains in the host directories you mounted):

```bash
docker compose -p medagent down --remove-orphans
```

---

## Service URLs / Ports

If not adjusting the ports, these are the default URLs:
* **Backend (FastAPI)**: `http://localhost:5001` (container port 5000)
* **MongoDB**: `localhost:27017`
* **Weaviate**: `http://localhost:8082` (container 8080)
* **Weaviate gRPC**: `localhost:50052` (container 50051)

---

## First start notes (models / caching)

Your backend Dockerfile pre-downloads several HuggingFace models during build (and warms up `evaluate` metrics). This can make the **first `docker build` slow**, but later runs are faster.

Runtime behavior:
* Container mounts `${MEDAGENT_HF_DATA_DIR}` to `/models-cache`
* Backend uses `/models-cache` as HF cache at runtime (env: `HF_HOME=/models-cache`, `HUGGINGFACE_HUB_CACHE=/models-cache`)
* Some models are also baked into the image under `/models` (build-time cache)
* Hierarchical index data is mounted to `/hierarchy_index_data` inside the backend container

---

## Datastores: how they are set up

All datastores are started automatically by Docker Compose and persist their data on the host via the paths you set in `.env`.

### MongoDB
* Docker image: `mongo:6.0`
* Credentials are set via:
  * `MONGO_INITDB_ROOT_USERNAME=mongo`
  * `MONGO_INITDB_ROOT_PASSWORD=mongo`
* Persistent storage:

  * `${MEDAGENT_MONGODB_DATA_DIR}:/data/db`

### Weaviate
* Docker image: `cr.weaviate.io/semitechnologies/weaviate:1.30.0`
* Persistence:
  * `${MEDAGENT_WEAVIATE_DATA_DIR}:/var/lib/weaviate`
* Note: `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED='true'` is currently enabled (fine for local dev; consider changing later for server deployment).

