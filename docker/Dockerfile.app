# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: final runtime image ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appgroup app/        ./app/
COPY --chown=appuser:appgroup training/   ./training/
COPY --chown=appuser:appgroup pipelines/  ./pipelines/
COPY --chown=appuser:appgroup pyproject.toml .

# Copy pre-trained model artifacts
# These are committed to git so Jenkins has access to them
# In production: replace this with a startup script that pulls from S3
COPY --chown=appuser:appgroup mlartifacts/model.pkl         ./mlartifacts/model.pkl
COPY --chown=appuser:appgroup mlartifacts/label_encoder.pkl ./mlartifacts/label_encoder.pkl
COPY --chown=appuser:appgroup mlartifacts/class_mapping.json ./mlartifacts/class_mapping.json

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
