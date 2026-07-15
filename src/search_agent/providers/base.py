import asyncio
import json
import logging
from typing import Protocol
from urllib.parse import urlparse

import httpx

from search_agent.models import RawSearchResult

logger = logging.getLogger(__name__)


class SearchProvider(Protocol):
    """A pluggable search backend.

    ``name`` doubles as the cache namespace and the label used in health
    checks and logs, so it must be stable and unique per provider.
    """

    name: str

    async def search(self, client: httpx.AsyncClient, query: str) -> list[RawSearchResult]: ...

    async def health(self, client: httpx.AsyncClient) -> bool: ...


async def read_capped_json(response: httpx.Response, max_bytes: int) -> dict | None:
    """Stream a JSON response body, aborting if it exceeds ``max_bytes``.

    Why: ``response.json()`` reads the full body unbounded. Search backends
    are trusted peers today, but a misbehaving or compromised peer could
    otherwise OOM the worker (and poison the cache slot for the query).
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            logger.warning("Search response exceeded %d bytes; aborting read", max_bytes)
            return None
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks))
    except json.JSONDecodeError:
        logger.warning("Search backend returned non-JSON body")
        return None


def is_valid_url(url: str) -> bool:
    """Accept only http/https URLs with a non-empty netloc."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def normalize_query(query: str) -> str:
    return query.strip().lower()


async def search_multiple(
    provider: SearchProvider, client: httpx.AsyncClient, queries: list[str]
) -> list[RawSearchResult]:
    """Execute multiple queries concurrently and deduplicate results by URL."""
    results_lists = await asyncio.gather(*(provider.search(client, q) for q in queries))

    all_results: list[RawSearchResult] = []
    seen_urls: set[str] = set()
    for results in results_lists:
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)

    return all_results
