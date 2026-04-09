import asyncio
import logging
from urllib.parse import urlparse

import httpx

from search_agent.config import settings
from search_agent.models import RawSearchResult

logger = logging.getLogger(__name__)


def _is_valid_url(url: str) -> bool:
    """Accept only http/https URLs with a non-empty netloc."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


async def search(client: httpx.AsyncClient, query: str) -> list[RawSearchResult]:
    """Execute a single search query against SearXNG and return structured results."""
    try:
        response = await client.get(
            f"{settings.searxng_url}/search",
            params={"q": query, "format": "json"},
            timeout=settings.searxng_timeout,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.exception("SearXNG request failed for query: %s", query)
        return []

    results = []
    for item in data.get("results", []):
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("content", "")
        engine = item.get("engine", "unknown")
        if title and url and _is_valid_url(url):
            results.append(RawSearchResult(title=title, url=url, snippet=snippet, engine=engine))

    return results


async def search_multiple(client: httpx.AsyncClient, queries: list[str]) -> list[RawSearchResult]:
    """Execute multiple queries concurrently and deduplicate results by URL."""
    results_lists = await asyncio.gather(*(search(client, q) for q in queries))

    all_results: list[RawSearchResult] = []
    seen_urls: set[str] = set()
    for results in results_lists:
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)

    return all_results
