import os

# Set test env vars before any imports that read settings
os.environ.setdefault("SEARCH_AGENT_LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("SEARCH_AGENT_LLM_API_KEY", "test-key")
os.environ.setdefault("SEARCH_AGENT_LLM_MODEL", "test-model")
os.environ.setdefault("SEARCH_AGENT_SEARXNG_URL", "http://localhost:8080")

# Pin settings the tests depend on so local .env overrides don't leak in
os.environ["SEARCH_AGENT_SEARCH_MAX_RESULTS"] = "15"
os.environ["SEARCH_AGENT_SEARCH_FETCH_PAGE_CONTENT"] = "false"
# Existing tests assume no caching; cache-specific tests opt in per-test.
os.environ["SEARCH_AGENT_CACHE_BACKEND"] = "disabled"
