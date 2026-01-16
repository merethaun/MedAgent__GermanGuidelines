# ---- Stage 1: cache HF models ----
FROM python:3.10-slim AS HFCACHE

RUN pip install --no-cache-dir "huggingface_hub>=0.23"
ENV HF_HOME=/models HUGGINGFACE_HUB_CACHE=/models

# Pre-cache all non-gated repos into the HF cache layout
RUN python -c "from huggingface_hub import snapshot_download; repos=['BAAI/bge-m3','BAAI/bge-reranker-large','BAAI/llm-embedder','xlm-roberta-large']; [snapshot_download(repo_id=r, cache_dir='/models') for r in repos]"

# OPTIONAL: gated model (Gemma). Build with: --build-arg HF_TOKEN=hf_xxx
ARG HF_TOKEN
ENV HUGGINGFACE_HUB_TOKEN=$HF_TOKEN
RUN if [ -n "$HUGGINGFACE_HUB_TOKEN" ]; then \
      python -c 'from huggingface_hub import snapshot_download; snapshot_download(repo_id="BAAI/bge-reranker-v2-gemma", cache_dir="/models")'; \
    else \
      echo "Skipping gated model BAAI/bge-reranker-v2-gemma (no HF token)"; \
    fi

# ---- Stage 2: app image ----
FROM python:3.10

ARG MODE=update
ENV MODE=${MODE}

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# IMPORTANT: paths must be relative (no leading /)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir evaluate rouge-score huggingface_hub

# Bring in cached models from stage 1
COPY --from=HFCACHE /models /models

# Warm evaluate metrics (online during build)
RUN python -c "import evaluate; [evaluate.load(n) for n in ['rouge','bleu','meteor','bertscore']]"

# Offline + local model paths at runtime
ENV HF_HOME=/models \
    HUGGINGFACE_HUB_CACHE=/models \
    HF_HUB_CACHE=/models \
    TRANSFORMERS_CACHE=/models \
    SENTENCE_TRANSFORMERS_HOME=/models \
    TRANSFORMERS_OFFLINE=0 \
    HF_HUB_OFFLINE=0 \
    LLM_EMBEDDER_PATH=/models/llm-embedder \
    BERTSCORE_MODEL_PATH=/models/xlm-roberta-large \
    BERTSCORE_MODEL_ID=xlm-roberta-large

# Copy app code
COPY src/ /src/

# Your data dir
ENV MEDAGENT_MONGODB_DATA_DIR=/data/mongodb

CMD if [ \"$MODE\" = \"update\" ]; then \
      echo \"Running in update mode\"; \
      uvicorn app.main:fast_app --host 0.0.0.0 --port 5000 --reload --loop asyncio; \
    elif [ \"$MODE\" = \"build\" ]; then \
      echo \"Running in build mode\"; \
      uvicorn app.main:fast_app --host 0.0.0.0 --port 5000 --workers 5 --loop asyncio; \
    else \
      echo \"Unknown MODE: $MODE. Please set MODE=update or MODE=build.\"; \
      exit 1; \
    fi
