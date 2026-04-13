# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install build dependencies needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency file first — Docker caches this layer
# until requirements.txt changes
COPY requirements.txt .

# Install into a local directory we'll copy to the final stage
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: final runtime image ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime system dependencies only — no compilers
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
# Ownership goes directly to appuser — no chown step needed
COPY --chown=appuser:appgroup app/        ./app/
COPY --chown=appuser:appgroup training/   ./training/
COPY --chown=appuser:appgroup pipelines/  ./pipelines/
COPY --chown=appuser:appgroup pyproject.toml .

# Create directories the app needs at runtime
RUN mkdir -p mlartifacts \
    && chown -R appuser:appgroup mlartifacts

# Switch to non-root user
USER appuser

# Expose FastAPI port
EXPOSE 8000

# Health check — Docker and Kubernetes both use this
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with gunicorn in production, uvicorn workers for async support
# --workers 2 is intentionally conservative for a 2-CPU pod
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]