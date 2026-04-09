FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# --- Dev target: includes test/lint tools ---
FROM base AS dev
RUN uv sync
EXPOSE 8001
CMD ["uv", "run", "uvicorn", "search_agent.main:app", "--host", "0.0.0.0", "--port", "8001"]

# --- Prod target: runtime deps only ---
FROM base AS prod
RUN uv sync --no-dev
EXPOSE 8001
CMD ["uv", "run", "--no-dev", "uvicorn", "search_agent.main:app", "--host", "0.0.0.0", "--port", "8001"]
