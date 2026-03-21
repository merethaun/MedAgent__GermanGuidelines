FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src/ /src/

CMD ["uvicorn", "app.main:main_app", "--host", "0.0.0.0", "--port", "5001", "--reload"]
