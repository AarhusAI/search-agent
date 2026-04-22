# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Search Agent — a FastAPI service that implements a 3-stage web search pipeline using Pydantic AI agents and SearXNG as the search backend. Also exposes search as an MCP tool.

## Commands

All Python commands run via docker compose (never directly on host). The Taskfile uses `docker compose exec` (requires running services), so start services first.

```bash
task compose-up                          # Start all services (required before other task commands)
task test                                # Run tests (uses exec)
task test -- tests/test_pipeline.py::TestSearchPipeline::test_pipeline_runs_all_stages  # Single test
task lint                                # Lint (src/ only)
task format                              # Format (src/ only)
task coding-standards:check              # Lint + format check
task coding-standards:apply              # Lint fix + format
task build:image                         # Build and push prod image to ghcr.io/aarhusai/search-agent
task build:image TAG=v1.0.0              # With custom tag
```

Alternative: direct docker compose (does not require running services):

```bash
docker compose run --rm --no-deps agent uv run pytest                    # Run all tests
docker compose run --rm --no-deps agent uv run ruff check src tests      # Lint
docker compose run --rm --no-deps agent uv run ruff format src tests     # Format
```

## Architecture

### 3-Stage Search Pipeline (`pipeline.py`)

1. **Query Planner** — Decomposes complex questions into up to `search_max_queries` targeted search queries via LLM. Skipped for "simple" queries (word/`?` thresholds in settings, plus a hardcoded complexity regex) controlled by `_is_simple_query()`.
2. **Search Executor** — Calls SearXNG via HTTP, runs multiple queries concurrently, deduplicates by URL, caps at `search_max_results`.
3. **(Optional) Page Fetch** — If `search_fetch_page_content=true`, `fetch.py` fetches the top `search_fetch_max_pages` result URLs and extracts main text via `trafilatura`; the extracted text lands in `RawSearchResult.content` for the synthesizer. Guarded by content-type check, byte cap, and an SSRF filter that rejects private/loopback/link-local hosts. MCP path is snippet-only regardless.
4. **Analyze + Synthesize** — Single combined agent (`analyze_synthesizer`) that filters, ranks, extracts passages, and generates a cited summary with `[1]`, `[2]` style inline citations.

### Key Modules

- `main.py` — FastAPI app with `/health`, `/api/v1/search` endpoints. Mounts MCP server at `/`.
- `pipeline.py` — Orchestrates the 3 stages with timeout handling (default 90s).
- `config.py` — `Settings` class using pydantic-settings. All env vars use `SEARCH_AGENT_` prefix.
- `deps.py` — Shared httpx client and Pydantic AI model, initialized at app startup via lifespan.
- `searxng.py` — SearXNG HTTP client with URL validation (http/https only). Warns on `unresponsive_engines` from the SearXNG response (e.g. Brave rate-limited) and, at DEBUG, logs which engines actually contributed results.
- `fetch.py` — Optional per-result page fetch with trafilatura extraction. Concurrent, with content-type / byte-size / SSRF guards. `trafilatura.extract` is run via `asyncio.to_thread` because it's sync.
- `models.py` — `SearchRequest`, `RawSearchResult` (now with optional `content` field populated by fetch), `SearchResult`, `Source`.
- `mcp_server.py` — FastMCP server exposing `search_web` tool. Uses `run_search_pipeline_raw` (steps 1+2 only, no LLM synthesis) so callers get raw results for their own citation handling (e.g. Open WebUI).
- `agents/` — Pydantic AI agent definitions. `analyze_synthesizer.py` is the combined analyze+synthesize agent.

### Data Flow

`SearchRequest(query, context)` → query planner → `[str]` queries → SearXNG → `[RawSearchResult]` → analyze_synthesizer → `SearchResult(summary, sources)`

## Configuration

All env vars use `SEARCH_AGENT_` prefix (via pydantic-settings). Key settings:

- `SEARCH_AGENT_DEBUG` (default: `false`) — sets `search_agent` and `pydantic_ai` loggers to DEBUG and logs full agent prompts + outputs, plus the SearXNG engine list per query. Does **not** enable `httpx`/`httpcore` DEBUG (those leak `Authorization` headers and full LLM response bodies); enable those manually if you need them.
- `SEARCH_AGENT_LLM_BASE_URL` (default: `http://localhost:11434/v1`) — OpenAI-compatible endpoint (Ollama, etc.)
- `SEARCH_AGENT_LLM_API_KEY`, `SEARCH_AGENT_LLM_MODEL` (default: `llama3`)
- `SEARCH_AGENT_LLM_STRICT_TOOLS` (default: `true`) — OpenAI strict tool definitions
- `SEARCH_AGENT_SEARXNG_URL` (default: `http://searxng:8080`)
- `SEARCH_AGENT_SEARXNG_TIMEOUT` (15s), `SEARCH_AGENT_SEARCH_PIPELINE_TIMEOUT` (90s), `SEARCH_AGENT_LLM_TIMEOUT` (60s)
- `SEARCH_AGENT_DATETIME_TIMEZONE` (default: `UTC`), `SEARCH_AGENT_DATETIME_FORMAT` — used in query planner prompts
- `SEARCH_AGENT_MCP_ALLOWED_HOSTS` (default: `["search-agent:8001","localhost:8001"]`)
- `SEARCH_AGENT_SEARCH_SKIP_PLANNER_FOR_SIMPLE_QUERIES` (default: `true`)
- `SEARCH_AGENT_SEARCH_MAX_QUERIES` (default: `3`) — cap planner output
- `SEARCH_AGENT_SEARCH_MAX_RESULTS` (default: `15`) — cap results reaching the synthesizer
- `SEARCH_AGENT_SEARCH_SIMPLE_QUERY_MAX_WORDS` (default: `15`), `SEARCH_AGENT_SEARCH_SIMPLE_QUERY_MAX_QUESTIONS` (default: `1`) — `_is_simple_query` thresholds
- `SEARCH_AGENT_SEARCH_FETCH_PAGE_CONTENT` (default: `false`) — fetch and extract main text from result pages via trafilatura; when enabled the synthesizer sees a `content` field per result in addition to the SearXNG `snippet`. MCP path (`search_web`) is snippet-only regardless.
- `SEARCH_AGENT_SEARCH_FETCH_MAX_PAGES` (5), `SEARCH_AGENT_SEARCH_FETCH_TIMEOUT` (10s), `SEARCH_AGENT_SEARCH_FETCH_MAX_CHARS` (5000), `SEARCH_AGENT_SEARCH_FETCH_MAX_BYTES` (2_000_000)
- Agent prompts overridable via `SEARCH_AGENT_SEARCH_QUERY_PLANNER_PROMPT`, `SEARCH_AGENT_SEARCH_ANALYZE_SYNTHESIZE_PROMPT`

## Testing

Tests mock all external services (LLM and SearXNG). `conftest.py` sets `SEARCH_AGENT_*` env vars before any module imports — this ordering matters because `config.py` reads env vars at module level via `settings = Settings()`.

pytest-asyncio is configured with `asyncio_mode = "auto"` so async tests don't need the `@pytest.mark.asyncio` decorator.

## Code Style

- Python 3.12+, ruff with rules: E, F, I, N, W, UP, B, RUF
- Line length: 100
- Async-first — all I/O uses async httpx and FastAPI async handlers

## Docker

Multi-stage Dockerfile with `dev` and `prod` targets. docker-compose defines two services: `agent` (container port 8001) and `searxng` (container port 8080), both with health checks — ports are not host-mapped (random host ports unless overridden). Services connect via a bridge `app` network and an external `frontend` network. Source is volume-mounted for live reload in dev. Build target is controlled by `ENV` variable (defaults to `dev`). Note: `Taskfile.yml` currently sets `SERVICE: search-agent`, which no longer matches the compose service name `agent` — task commands that use `docker compose exec {{.SERVICE}}` will fail until that var is updated.

## Important rules

- **Never read `.env` files** — they contain secrets. Use `docker-compose.yml` or `config.py` to understand env vars.
- **Always use docker compose** to run Python commands — never run `uv` or Python directly on the host.
