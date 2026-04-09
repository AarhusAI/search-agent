from pydantic import BaseModel, field_validator


class RawSearchResult(BaseModel):
    """A single result from SearXNG."""

    title: str
    url: str
    snippet: str
    engine: str

    @field_validator("title")
    @classmethod
    def truncate_title(cls, v: str) -> str:
        return v[:200] if len(v) > 200 else v

    @field_validator("snippet")
    @classmethod
    def truncate_snippet(cls, v: str) -> str:
        return v[:500] if len(v) > 500 else v


class Source(BaseModel):
    """A cited source in the final output."""

    title: str
    url: str


class RelevantPassage(BaseModel):
    """A passage extracted by the analyzer agent."""

    text: str
    source_url: str
    relevance: str


class AnalyzedResults(BaseModel):
    """Output of the analyzer agent."""

    relevant_passages: list[RelevantPassage]
    sources: list[Source]


class SearchResult(BaseModel):
    """Final pipeline output — sourced summary with citations."""

    summary: str
    sources: list[Source]


class SearchRequest(BaseModel):
    """Incoming search request from the backend."""

    query: str
    context: str = ""
