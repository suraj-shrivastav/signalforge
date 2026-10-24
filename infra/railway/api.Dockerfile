# API and worker image for Railway. Build context: the repository root.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Dependencies first so code changes reuse the cached layer.
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY apps ./apps
COPY alembic.ini ./

# Railway sets PORT. The web app reaches this service over it.
CMD ["sh", "-c", "uvicorn apps.api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
