# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Search Agent — a FastAPI service that implements a 3-stage web search pipeline using Pydantic AI agents and SearXNG as the search backend. Also exposes search as an MCP tool.

## Commands

```bash
uv sync                           # Install dependencies
uv run pytest                     # Run all tests
uv run pytest tests/test_pipeline.py::TestSearchPipeline::test_pipeline_runs_all_stages  # Single test
uv run ruff check src tests       # Lint
uv run ruff format src tests      # Format
uv run uvicorn search_agent.main:app --reload --port 8001  # Run dev server
docker compose up -d              # Start search-agent + SearXNG
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
- Agent prompts overridable via `SEARCH_AGENT_SEARCH_QUERY_PLANNER_PROMPT`, `SEARCH_AGENT_SEARCH_ANALYZER_PROMPT`, `SEARCH_AGENT_SEARCH_SYNTHESIZER_PROMPT`, `SEARCH_AGENT_SEARCH_ANALYZE_SYNTHESIZE_PROMPT`

## Testing

Tests mock all external services (LLM and SearXNG). `conftest.py` sets `SEARCH_AGENT_*` env vars before any module imports — this ordering matters because `config.py` reads env vars at module level via `settings = Settings()`.

pytest-asyncio is configured with `asyncio_mode = "auto"` so async tests don't need the `@pytest.mark.asyncio` decorator.

## Code Style

- Python 3.12+, ruff with rules: E, F, I, N, W, UP, B, RUF
- Line length: 100
- Async-first — all I/O uses async httpx and FastAPI async handlers

## Docker

Multi-stage Dockerfile with `dev` and `prod` targets. docker-compose runs search-agent (port 8001) and SearXNG (port 8080) with health checks on both. Source is volume-mounted for live reload in dev.
