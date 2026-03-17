FROM python:3.12-slim

ARG MODE=build
ENV MODE=${MODE}
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV HF_HOME=/models/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libgomp1 && \
    update-ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src/ /src/

CMD if [ "$MODE" = "update" ]; then \
      echo "Running in update mode"; \
      uvicorn app.main:main_app --host 0.0.0.0 --port 5000 --reload --loop asyncio; \
    elif [ "$MODE" = "build" ]; then \
      echo "Running in build mode"; \
      uvicorn app.main:main_app --host 0.0.0.0 --port 5000 --workers 1 --loop asyncio; \
    else \
      echo "Unknown MODE: $MODE. Please set MODE=update or MODE=build."; \
      exit 1; \
    fi
