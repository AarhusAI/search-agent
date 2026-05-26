import asyncio
import json
import logging
from urllib.parse import urlparse

import httpx

from search_agent import cache
from search_agent.config import settings
from search_agent.models import RawSearchResult

logger = logging.getLogger(__name__)


async def _read_capped_json(response: httpx.Response, max_bytes: int) -> dict | None:
    """Stream a JSON response body, aborting if it exceeds ``max_bytes``.

    Why: ``response.json()`` reads the full body unbounded. SearXNG is a
    trusted peer today, but a misbehaving or compromised peer could
    otherwise OOM the worker (and poison the cache slot for the query).
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            logger.warning("SearXNG response exceeded %d bytes; aborting read", max_bytes)
            return None
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks))
    except json.JSONDecodeError:
        logger.warning("SearXNG returned non-JSON body")
        return None


def _is_valid_url(url: str) -> bool:
    """Accept only http/https URLs with a non-empty netloc."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _normalize_query(query: str) -> str:
    return query.strip().lower()


async def search(client: httpx.AsyncClient, query: str) -> list[RawSearchResult]:
    """Execute a single search query against SearXNG and return structured results."""
    cache_key = cache.make_key("searxng", _normalize_query(query), settings.searxng_url)
    cached = await cache.get_json(cache_key)
    if cached is not None:
        logger.debug("searxng cache hit query=%r", query)
        return [RawSearchResult.model_validate(item) for item in cached]

    try:
        async with client.stream(
            "GET",
            f"{settings.searxng_url}/search",
            params={"q": query, "format": "json"},
            timeout=settings.searxng_timeout,
        ) as response:
            response.raise_for_status()
            data = await _read_capped_json(response, settings.searxng_max_response_bytes)
    except httpx.HTTPError:
        logger.exception("SearXNG request failed for query: %s", query)
        return []
    if data is None:
        return []

    unresponsive = data.get("unresponsive_engines") or []
    if unresponsive:
        logger.warning("SearXNG engines unresponsive for query=%r: %s", query, unresponsive)
    raw_results = data.get("results", [])
    logger.debug(
        "SearXNG response for query=%r: %d results, engines=%s",
        query,
        len(raw_results),
        sorted({item.get("engine", "unknown") for item in raw_results}),
    )

    results = []
    for item in raw_results:
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("content", "")
        engine = item.get("engine", "unknown")
        if title and url and _is_valid_url(url):
            results.append(RawSearchResult(title=title, url=url, snippet=snippet, engine=engine))

    if results:
        await cache.set_json(
            cache_key,
            [r.model_dump(mode="json") for r in results],
            ttl=settings.cache_searxng_ttl,
        )
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
