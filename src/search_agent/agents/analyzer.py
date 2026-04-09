from pydantic_ai import Agent

from search_agent.config import settings
from search_agent.deps import PipelineDeps, create_model
from search_agent.models import AnalyzedResults

analyzer = Agent(
    create_model(),
    output_type=AnalyzedResults,
    instructions=settings.search_analyzer_prompt,
    deps_type=PipelineDeps,
)
