# ------------------------------------------------------------------ #
# Builder stage
# ------------------------------------------------------------------ #
FROM python:3.12 AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip wheel

COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

# ------------------------------------------------------------------ #
# Runtime stage
# ------------------------------------------------------------------ #
FROM python:3.12-slim AS runtime

# Create non-root user first
RUN groupadd -r autofix && useradd -r -g autofix autofix

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy source files and set ownership in one layer
COPY --chown=autofix:autofix app/ ./app/
COPY --chown=autofix:autofix alembic/ ./alembic/
COPY --chown=autofix:autofix alembic.ini .

USER autofix

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
