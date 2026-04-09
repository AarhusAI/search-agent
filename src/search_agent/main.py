import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from search_agent.config import settings
from search_agent.deps import close_shared_clients, get_http_client, init_shared_clients
from search_agent.mcp_server import mcp
from search_agent.models import SearchRequest, SearchResult
from search_agent.pipeline import run_search_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_shared_clients()
    async with mcp.session_manager.run():
        yield
    await close_shared_clients()


app = FastAPI(title="Search Agent", lifespan=lifespan)


@app.get("/health")
async def health(deep: bool = False):
    if not deep:
        return {"status": "ok"}

    try:
        client = get_http_client()
        response = await client.get(f"{settings.searxng_url}/healthz", timeout=5.0)
        response.raise_for_status()
        return {"status": "ok", "searxng": "reachable"}
    except (httpx.HTTPError, RuntimeError):
        logger.exception("Deep health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "searxng": "unreachable"},
        )


@app.post("/api/v1/search", response_model=SearchResult)
async def search(request: SearchRequest) -> SearchResult:
    """Run the search pipeline and return a sourced summary."""
    logger.info("Search request: query=%r context=%r", request.query, request.context)
    try:
        result = await run_search_pipeline(query=request.query, context=request.context)
        return result
    except Exception:
        logger.exception("Search pipeline failed")
        return JSONResponse(
            status_code=500,
            content={"summary": "Search failed due to an internal error.", "sources": []},
        )


app.mount("/", mcp.streamable_http_app())
