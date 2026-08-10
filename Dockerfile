# Artgents Backend — Cloud Run container
# Uses uv for fast, reproducible dependency installation from uv.lock.

FROM python:3.12-slim

WORKDIR /app

# Install uv (standalone binary, no pip bootstrap needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for Docker layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies only (no dev group)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source and config
COPY src/ src/
COPY config/ config/

# Install the project itself (editable not needed in container)
RUN uv sync --frozen --no-dev

# Cloud Run sets PORT env var (default 8080)
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

# Run with uvicorn; Cloud Run sends SIGTERM for graceful shutdown
CMD ["uv", "run", "uvicorn", "artgents.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
