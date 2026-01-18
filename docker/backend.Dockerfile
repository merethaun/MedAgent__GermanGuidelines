FROM python:3.13-slim

ARG MODE=build
ENV MODE=${MODE}

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /src/

CMD if [ "$MODE" = "update" ]; then \
      echo "Running in update mode"; \
      uvicorn app.main:fast_app --host 0.0.0.0 --port 5000 --reload --loop asyncio; \
    elif [ "$MODE" = "build" ]; then \
      echo "Running in build mode"; \
      uvicorn app.main:fast_app --host 0.0.0.0 --port 5000 --workers 5 --loop asyncio; \
    else \
      echo "Unknown MODE: $MODE. Please set MODE=update or MODE=build."; \
      exit 1; \
    fi
