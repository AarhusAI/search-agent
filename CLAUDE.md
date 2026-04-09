# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Search Agent — a FastAPI service that implements a 3-stage web search pipeline using Pydantic AI agents and SearXNG as the search backend. Also exposes search as an MCP tool.

## Commands

All Python commands run via docker compose (never directly on host):

```bash
docker compose up -d                                            # Start search-agent + SearXNG
docker compose run --rm --no-deps search-agent uv run pytest    # Run all tests
docker compose run --rm --no-deps search-agent uv run pytest tests/test_pipeline.py::TestSearchPipeline::test_pipeline_runs_all_stages  # Single test
docker compose run --rm --no-deps search-agent uv run ruff check src tests   # Lint
docker compose run --rm --no-deps search-agent uv run ruff format src tests  # Format
```

Or via [go-task](https://taskfile.dev/) (wraps docker compose):

```bash
task compose-up       # Start all services
task test             # Run tests
task lint             # Lint
task format           # Format
task coding-standards:check   # Lint + format check
task coding-standards:apply   # Lint fix + format
task build:image              # Build and push prod image to ghcr.io/aarhusai/search-agent
task build:image TAG=v1.0.0   # With custom tag
```

## Architecture

### 3-Stage Search Pipeline (`pipeline.py`)

1. **Query Planner** — Decomposes complex questions into 1-3 targeted search queries via LLM. Skipped for "simple" queries (<=15 words, no comparison patterns, single question mark) controlled by `_is_simple_query()`.
2. **Search Executor** — Calls SearXNG via HTTP, runs multiple queries concurrently, deduplicates by URL, caps at 15 results.
3. **Analyze + Synthesize** — Single combined agent (`analyze_synthesizer`) that filters, ranks, extracts passages, and generates a cited summary with `[1]`, `[2]` style inline citations.

### Key Modules

- `main.py` — FastAPI app with `/health`, `/api/v1/search` endpoints. Mounts MCP server at `/`.
- `pipeline.py` — Orchestrates the 3 stages with timeout handling (default 90s).
- `config.py` — `Settings` class using pydantic-settings. All env vars use `SEARCH_AGENT_` prefix.
- `deps.py` — Shared httpx client and Pydantic AI model, initialized at app startup via lifespan.
- `searxng.py` — SearXNG HTTP client with URL validation (http/https only).
- `models.py` — `SearchRequest`, `RawSearchResult`, `SearchResult`, `Source`.
- `mcp_server.py` — FastMCP server exposing `web_search` tool.
- `agents/` — Pydantic AI agent definitions. `analyze_synthesizer.py` is the combined analyze+synthesize agent.

### Data Flow

`SearchRequest(query, context)` → query planner → `[str]` queries → SearXNG → `[RawSearchResult]` → analyze_synthesizer → `SearchResult(summary, sources)`

## Configuration

All env vars use `SEARCH_AGENT_` prefix (via pydantic-settings). Key settings:

- `SEARCH_AGENT_LLM_BASE_URL` (default: `http://localhost:11434/v1`) — OpenAI-compatible endpoint (Ollama, etc.)
- `SEARCH_AGENT_LLM_API_KEY`, `SEARCH_AGENT_LLM_MODEL` (default: `llama3`)
- `SEARCH_AGENT_SEARXNG_URL` (default: `http://searxng:8080`)
- `SEARCH_AGENT_SEARXNG_TIMEOUT` (15s), `SEARCH_AGENT_SEARCH_PIPELINE_TIMEOUT` (90s), `SEARCH_AGENT_LLM_TIMEOUT` (60s)
- Agent prompts overridable via `SEARCH_AGENT_SEARCH_QUERY_PLANNER_PROMPT`, `SEARCH_AGENT_SEARCH_ANALYZE_SYNTHESIZE_PROMPT`

## Testing

Tests mock all external services (LLM and SearXNG). `conftest.py` sets `SEARCH_AGENT_*` env vars before any module imports — this ordering matters because `config.py` reads env vars at module level via `settings = Settings()`.

pytest-asyncio is configured with `asyncio_mode = "auto"` so async tests don't need the `@pytest.mark.asyncio` decorator.

## Code Style

- Python 3.12+, ruff with rules: E, F, I, N, W, UP, B, RUF
- Line length: 100
- Async-first — all I/O uses async httpx and FastAPI async handlers

## Docker

Multi-stage Dockerfile with `dev` and `prod` targets. docker-compose runs search-agent (port 8001) and SearXNG (port 8080) with health checks on both. Source is volume-mounted for live reload in dev. Build target is controlled by `ENV` variable (defaults to `dev`).

## Important rules

- **Never read `.env` files** — they contain secrets. Use `docker-compose.yml` or `config.py` to understand env vars.
- **Always use docker compose** to run Python commands — never run `uv` or Python directly on the host.
