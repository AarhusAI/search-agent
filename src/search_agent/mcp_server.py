from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from search_agent.config import settings
from search_agent.models import SearchResult
from search_agent.pipeline import run_search_pipeline

mcp = FastMCP(
    "search-agent",
    transport_security=TransportSecuritySettings(
        allowed_hosts=settings.mcp_allowed_hosts,
    ),
)


@mcp.tool()
async def web_search(query: str, context: str = "") -> str:
    """Search the web for current information.

    Use this when the user asks about recent events, facts you're unsure about,
    or anything that benefits from up-to-date web data.

    Args:
        query: The search query to look up on the web.
        context: Optional conversation context to help refine the search.

    Returns:
        JSON string with 'summary' and 'sources' keys.
    """
    result: SearchResult = await run_search_pipeline(query=query, context=context)
    return result.model_dump_json()
