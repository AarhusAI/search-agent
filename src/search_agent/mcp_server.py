import json

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from search_agent.config import settings
from search_agent.models import RawSearchResult
from search_agent.pipeline import run_search_pipeline_raw

mcp = FastMCP(
    "search-agent",
    transport_security=TransportSecuritySettings(
        allowed_hosts=settings.mcp_allowed_hosts,
    ),
)


@mcp.tool()
async def search_web(query: str, context: str = "") -> str:
    """Search the web for current information.

    Use this when the user asks about recent events, facts you're unsure about,
    or anything that benefits from up-to-date web data.

    Args:
        query: The search query to look up on the web.
        context: Optional conversation context to help refine the search.

    Returns:
        JSON array of search results, each with 'title', 'link', and 'snippet' keys.
    """
    raw_results: list[RawSearchResult] = await run_search_pipeline_raw(query=query, context=context)
    formatted = [{"title": r.title, "link": r.url, "snippet": r.snippet} for r in raw_results]
    return json.dumps(formatted)
