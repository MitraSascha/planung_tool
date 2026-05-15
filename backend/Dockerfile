FROM node:22-bookworm-slim AS node

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/models/huggingface
ENV TRANSFORMERS_CACHE=/models/huggingface

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local /usr/local

RUN npm install -g @openai/codex@0.130.0 \
    && npm cache clean --force

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /models/huggingface \
    && python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_multi_pii-v1')" \
    && chown -R appuser:appuser /models

COPY app ./app

RUN mkdir -p /storage/workspaces /storage/projects /storage/uploads \
    && chown -R appuser:appuser /storage /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
