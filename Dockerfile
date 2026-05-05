FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

# Non-root user matching the k8s securityContext (runAsUser/runAsGroup: 1000).
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash app

WORKDIR /app
RUN chown app:app /app

USER app

# Copy project files as the app user so /app/.venv (created by `uv sync` below)
# is owned by UID 1000 from the start.
COPY --chown=app:app pyproject.toml uv.lock ./
COPY --chown=app:app src/ ./src/

# --- Dev target: includes test/lint tools ---
FROM base AS dev
RUN uv sync --frozen
EXPOSE 8001
CMD ["uv", "run", "--no-sync", "uvicorn", "search_agent.main:app", "--host", "0.0.0.0", "--port", "8001"]

# --- Prod target: runtime deps only ---
FROM base AS prod
RUN uv sync --frozen --no-dev
EXPOSE 8001
CMD ["uv", "run", "--no-sync", "--no-dev", "uvicorn", "search_agent.main:app", "--host", "0.0.0.0", "--port", "8001"]
