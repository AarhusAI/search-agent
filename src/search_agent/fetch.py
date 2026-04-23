import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
import trafilatura

from search_agent import cache
from search_agent.config import settings
from search_agent.models import RawSearchResult
from search_agent.searxng import _is_valid_url

logger = logging.getLogger(__name__)


async def _host_is_public(host: str) -> bool:
    """Return True only if every resolved address for host is public routable."""
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return False
    return bool(infos)


async def _fetch_one(
    client: httpx.AsyncClient,
    url: str,
    timeout: float,
    max_chars: int,
    max_bytes: int,
) -> str | None:
    """Fetch a URL and return extracted main text, or None on any failure.

    Results are cached: successful extracts for `cache_fetch_ttl`, failures
    (invalid URL, SSRF block, HTTP error, empty extract) for the shorter
    `cache_fetch_negative_ttl` so transient failures recover quickly.
    """
    cache_key = cache.make_key("fetch", url, max_chars)
    cached = await cache.get_json(cache_key)
    if cached is not None:
        logger.debug("fetch cache hit url=%s ok=%s", url, cached.get("ok"))
        return cached.get("text") if cached.get("ok") else None

    text = await _fetch_one_uncached(client, url, timeout, max_chars, max_bytes)
    if text:
        await cache.set_json(cache_key, {"ok": True, "text": text}, ttl=settings.cache_fetch_ttl)
    else:
        await cache.set_json(cache_key, {"ok": False}, ttl=settings.cache_fetch_negative_ttl)
    return text


async def _fetch_one_uncached(
    client: httpx.AsyncClient,
    url: str,
    timeout: float,
    max_chars: int,
    max_bytes: int,
) -> str | None:
    if not _is_valid_url(url):
        return None

    host = urlparse(url).hostname
    if not host or not await _host_is_public(host):
        logger.debug("Fetch blocked (non-public host): %s", url)
        return None

    try:
        async with client.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
            if response.status_code >= 400:
                return None
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("text/html"):
                return None

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    logger.debug("Fetch aborted (size cap %d exceeded): %s", max_bytes, url)
                    return None
                chunks.append(chunk)
            body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    except (httpx.HTTPError, UnicodeDecodeError):
        logger.debug("Fetch failed: %s", url, exc_info=True)
        return None

    text = await asyncio.to_thread(
        trafilatura.extract,
        body,
        include_comments=False,
        include_tables=False,
        output_format="markdown",
    )
    if not text:
        return None
    return text[:max_chars]


async def fetch_pages(
    client: httpx.AsyncClient,
    results: list[RawSearchResult],
    max_pages: int,
    timeout: float,
    max_chars: int,
    max_bytes: int,
) -> list[RawSearchResult]:
    """Fetch and extract main content for up to max_pages results.

    Results beyond max_pages keep content=None. Any fetch failure leaves
    content=None so the pipeline continues with just the snippet.
    """
    if max_pages <= 0 or not results:
        return results

    targets = results[:max_pages]
    extracted = await asyncio.gather(
        *(_fetch_one(client, r.url, timeout, max_chars, max_bytes) for r in targets)
    )
    for result, text in zip(targets, extracted, strict=True):
        result.content = text

    fetched = sum(1 for t in extracted if t)
    logger.info("Fetched %d/%d pages with extractable content", fetched, len(targets))
    return results
