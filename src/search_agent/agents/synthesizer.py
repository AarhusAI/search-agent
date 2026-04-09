from pydantic_ai import Agent

from search_agent.config import settings
from search_agent.deps import PipelineDeps, create_model
from search_agent.models import SearchResult

synthesizer = Agent(
    create_model(),
    output_type=SearchResult,
    instructions=settings.search_synthesizer_prompt,
    deps_type=PipelineDeps,
)
