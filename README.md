# Search Agent

A FastAPI service that implements a 3-stage web search pipeline using [Pydantic AI](https://ai.pydantic.dev/) agents and [SearXNG](https://docs.searxng.org/) as the search backend. Also exposes search as an [MCP](https://modelcontextprotocol.io/) tool for integration with LLM-powered applications (e.g. Open WebUI).

## Architecture

```
SearchRequest(query, context)
        |
        v
  Query Planner        -- decomposes complex questions into 1-3 targeted queries (LLM)
        |                  skipped for simple queries (<=15 words, single topic)
        v
  Search Executor      -- calls SearXNG, runs queries concurrently, deduplicates, caps at 15 results
        |
        v
  Analyze+Synthesize   -- filters, ranks, extracts passages, generates cited summary (LLM)
        |
        v
  SearchResult(summary, sources)
```

### Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check. Pass `?deep=true` to also verify SearXNG connectivity. |
| `/api/v1/search` | POST | Run the full search pipeline. Accepts `{"query": "...", "context": "..."}`. |
| `/` | - | MCP Streamable HTTP transport. Exposes `search_web` tool (steps 1+2 only, no LLM synthesis). |

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [Task](https://taskfile.dev/) (optional, for convenience commands)
- Access to an OpenAI-compatible LLM endpoint (Ollama, vLLM, OpenAI, etc.)

## Getting Started

1. **Copy the example env file** and fill in your LLM settings:

   ```bash
   cp .env.example .env
   ```

   Required variables:

   | Variable | Description |
   |---|---|
   | `SEARCH_AGENT_LLM_BASE_URL` | OpenAI-compatible API base URL |
   | `SEARCH_AGENT_LLM_API_KEY` | API key for the LLM endpoint |
   | `SEARCH_AGENT_LLM_MODEL` | Model name to use |

2. **Start the services:**

   ```bash
   task compose-up
   ```

   Or without Task:

   ```bash
   docker compose up --detach --remove-orphans
   ```

   This starts:
   - **search-agent** on container port `8001` (random host port unless overridden)
   - **SearXNG** on container port `8080` (random host port unless overridden)

3. **Verify it's running:**

   ```bash
   # Find the mapped host port
   docker compose port search-agent 8001

   # Check health
   curl http://localhost:<port>/health
   ```

## Configuration

All environment variables use the `SEARCH_AGENT_` prefix (via pydantic-settings).

| Variable | Default | Description |
|---|---|---|
| `SEARCH_AGENT_LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible LLM endpoint |
| `SEARCH_AGENT_LLM_API_KEY` | `not-needed` | API key for the LLM |
| `SEARCH_AGENT_LLM_MODEL` | `llama3` | Model name |
| `SEARCH_AGENT_LLM_STRICT_TOOLS` | `true` | OpenAI strict tool definitions. Set to `false` for models that don't support it (e.g. Mistral). |
| `SEARCH_AGENT_LLM_TIMEOUT` | `60` | LLM request timeout (seconds) |
| `SEARCH_AGENT_SEARXNG_URL` | `http://searxng:8080` | SearXNG instance URL |
| `SEARCH_AGENT_SEARXNG_TIMEOUT` | `15` | SearXNG request timeout (seconds) |
| `SEARCH_AGENT_SEARCH_PIPELINE_TIMEOUT` | `90` | Overall pipeline timeout (seconds) |
| `SEARCH_AGENT_DATETIME_TIMEZONE` | `UTC` | Timezone for date/time in query planner prompts |
| `SEARCH_AGENT_DATETIME_FORMAT` | `%A, %B %-d, %Y, %H:%M %Z` | Date format string |
| `SEARCH_AGENT_MCP_ALLOWED_HOSTS` | `["search-agent:8001","localhost:8001"]` | Hosts allowed for MCP transport |
| `SEARCH_AGENT_SEARCH_SKIP_PLANNER_FOR_SIMPLE_QUERIES` | `true` | Skip query planner for simple queries |
| `SEARCH_AGENT_SEARCH_QUERY_PLANNER_PROMPT` | *(built-in)* | Override the query planner system prompt |
| `SEARCH_AGENT_SEARCH_ANALYZE_SYNTHESIZE_PROMPT` | *(built-in)* | Override the analyze+synthesize system prompt |

## Development

All Python commands run via Docker Compose -- never directly on the host.

### Task commands (requires running services)

```bash
task compose-up                          # Start all services (required first)
task test                                # Run tests
task test -- tests/test_pipeline.py      # Run a specific test file
task lint                                # Lint (src/ only)
task format                              # Format (src/ only)
task coding-standards:check              # Lint + format check
task coding-standards:apply              # Lint fix + format
```

### Direct Docker Compose (does not require running services)

```bash
docker compose run --rm --no-deps search-agent uv run pytest
docker compose run --rm --no-deps search-agent uv run ruff check src tests
docker compose run --rm --no-deps search-agent uv run ruff format src tests
```

### Building the production image

```bash
task build:image                         # Build and push with :latest tag
task build:image TAG=v1.0.0              # Build and push with custom tag
```

Image is pushed to `ghcr.io/aarhusai/search-agent`.

## Docker

The Dockerfile uses multi-stage builds with `dev` and `prod` targets. The build target is controlled by the `ENV` variable (defaults to `dev`).

- **dev** -- includes test/lint tools, source is volume-mounted for live reload
- **prod** -- runtime dependencies only (`uv sync --no-dev`)

Services connect via a `bridge` network (`app`) and an external `frontend` network. SearXNG configuration lives in `.docker/searxng/settings.yml`.

## Tech Stack

- Python 3.12+
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- [Pydantic AI](https://ai.pydantic.dev/) for LLM agents
- [SearXNG](https://docs.searxng.org/) for web search
- [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) for tool integration
- [httpx](https://www.python-httpx.org/) for async HTTP
- [uv](https://docs.astral.sh/uv/) for package management
- [ruff](https://docs.astral.sh/ruff/) for linting and formatting
- [Task](https://taskfile.dev/) for task running
