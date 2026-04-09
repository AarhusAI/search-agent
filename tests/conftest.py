import os

# Set test env vars before any imports that read settings
os.environ.setdefault("SEARCH_AGENT_LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("SEARCH_AGENT_LLM_API_KEY", "test-key")
os.environ.setdefault("SEARCH_AGENT_LLM_MODEL", "test-model")
os.environ.setdefault("SEARCH_AGENT_SEARXNG_URL", "http://localhost:8080")
