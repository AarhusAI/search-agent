import asyncio
import json
import logging
import re
import time
import zoneinfo
from datetime import datetime

from search_agent.agents.analyze_synthesizer import analyze_synthesizer
from search_agent.agents.query_planner import query_planner
from search_agent.config import settings
from search_agent.deps import PipelineDeps, get_http_client, get_model
from search_agent.models import SearchResult
from search_agent.searxng import search_multiple

logger = logging.getLogger(__name__)

# Patterns that suggest a multi-faceted query needing decomposition
_COMPLEX_QUERY_PATTERNS = re.compile(
    r"\b(compare|vs\.?|versus|difference between|pros and cons|advantages and disadvantages"
    r"|on one hand|similarities and differences)\b",
    re.IGNORECASE,
)


def _is_simple_query(query: str) -> bool:
    """Heuristic: return True if the query is simple enough to skip the planner."""
    words = query.split()
    if len(words) > 15:
        return False
    if _COMPLEX_QUERY_PATTERNS.search(query):
        return False
    # Multiple questions (contains more than one '?')
    if query.count("?") > 1:
        return False
    return True


async def run_search_pipeline(query: str, context: str = "") -> SearchResult:
    """Run the full search pipeline: plan → search → analyze+synthesize."""
    try:
        async with asyncio.timeout(settings.search_pipeline_timeout):
            return await _run_search_pipeline(query, context)
    except TimeoutError:
        logger.warning(
            "Search pipeline timed out after %ds for query: %s",
            settings.search_pipeline_timeout,
            query,
        )
        return SearchResult(summary="Search timed out. Please try again.", sources=[])


async def _run_search_pipeline(query: str, context: str = "") -> SearchResult:
    """Inner pipeline logic wrapped by the timeout in run_search_pipeline."""
    pipeline_start = time.monotonic()
    model = get_model()
    http_client = get_http_client()
    deps = PipelineDeps(http_client=http_client, model=model)

    # Step 1: Plan search queries (or skip for simple queries)
    tz = zoneinfo.ZoneInfo(settings.datetime_timezone)
    now = datetime.now(tz=tz).strftime(settings.datetime_format)

    if settings.search_skip_planner_for_simple_queries and _is_simple_query(query):
        search_queries = [query]
        planner_time = 0.0
        logger.info("Skipped query planner (simple query): %s", search_queries)
    else:
        planner_start = time.monotonic()
        prompt = f"Current date and time: {now}\nQuestion: {query}"
        if context:
            prompt += f"\nConversation context: {context}"
        plan_result = await query_planner.run(prompt, deps=deps, model=model)
        search_queries = plan_result.output
        planner_time = time.monotonic() - planner_start
        logger.info(
            "Query planner produced %d queries in %.1fs: %s",
            len(search_queries),
            planner_time,
            search_queries,
        )

    # Step 2: Execute searches (no LLM, just HTTP → SearXNG)
    search_start = time.monotonic()
    raw_results = await search_multiple(http_client, search_queries)
    search_time = time.monotonic() - search_start
    logger.info("SearXNG returned %d results in %.1fs", len(raw_results), search_time)

    if not raw_results:
        total_time = time.monotonic() - pipeline_start
        logger.info(
            "Search pipeline: planner=%.1fs search=%.1fs total=%.1fs (no results)",
            planner_time,
            search_time,
            total_time,
        )
        return SearchResult(summary="No search results found.", sources=[])

    # Limit results to avoid overwhelming the LLM
    raw_results = raw_results[:15]

    # Step 3: Analyze and synthesize in one pass
    analyze_synth_start = time.monotonic()
    raw_json = json.dumps([r.model_dump() for r in raw_results])
    result = await analyze_synthesizer.run(
        (
            f"Question: {query}\n"
            f"--- BEGIN EXTERNAL SEARCH RESULTS ---\n"
            f"{raw_json}\n"
            f"--- END EXTERNAL SEARCH RESULTS ---"
        ),
        deps=deps,
        model=model,
    )
    analyze_synth_time = time.monotonic() - analyze_synth_start

    total_time = time.monotonic() - pipeline_start
    logger.info(
        "Search pipeline: planner=%.1fs search=%.1fs analyze_synthesize=%.1fs total=%.1fs",
        planner_time,
        search_time,
        analyze_synth_time,
        total_time,
    )

    return result.output
