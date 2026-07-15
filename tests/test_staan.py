from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from search_agent.cache import InMemoryBackend, set_backend_for_testing
from search_agent.config import settings
from search_agent.providers.staan import StaanProvider, _build_params
from tests.conftest import make_stream_mock

provider = StaanProvider()


def make_staan_body(results: list[dict]) -> dict:
    return {"search_id": "test", "web": {"results": results}}


def full_result(**overrides) -> dict:
    item = {
        "title": "Vector databases",
        "url": "https://example.com/vector-dbs",
        "snippet": "A deep dive into vector databases.",
        "hostname": "example.com",
        "published_date": "2024-09-10T00:00:00.000Z",
        "full_content": {
            "text": "# Comparing vector databases\n\nThis guide covers everything.",
            "format": "markdown",
            "length": 60,
        },
    }
    item.update(overrides)
    return item


class TestBuildParams:
    def test_full_content_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "staan_enrichment", "full_content")
        params = _build_params("test")
        assert params["q"] == "test"
        assert params["market"] == settings.staan_market
        assert params["full_content"] == "markdown"
        assert "extra_snippets" not in params

    def test_extra_snippets_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "staan_enrichment", "extra_snippets")
        params = _build_params("test")
        assert params["extra_snippets"] == "true"
        assert params["max_snippets"] == settings.staan_max_snippets
        assert params["min_score"] == settings.staan_min_score
        assert "full_content" not in params

    def test_none_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "staan_enrichment", "none")
        params = _build_params("test")
        assert "full_content" not in params
        assert "extra_snippets" not in params


class TestStaanSearch:
    async def test_maps_fields_including_content(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(
            return_value=make_stream_mock(make_staan_body([full_result()]))
        )

        results = await provider.search(mock_client, "vector databases")

        assert len(results) == 1
        r = results[0]
        assert r.title == "Vector databases"
        assert r.url == "https://example.com/vector-dbs"
        assert r.snippet == "A deep dive into vector databases."
        assert r.engine == "staan"
        assert r.published_date == "2024-09-10T00:00:00.000Z"
        assert r.content is not None
        assert r.content.startswith("# Comparing vector databases")

    async def test_missing_full_content_leaves_content_none(self):
        item = full_result()
        del item["full_content"]
        del item["published_date"]
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(return_value=make_stream_mock(make_staan_body([item])))

        results = await provider.search(mock_client, "q")

        assert results[0].content is None
        assert results[0].published_date is None

    async def test_extra_snippets_joined_into_content(self):
        item = full_result()
        del item["full_content"]
        item["extra_snippets"] = [
            {"chunk": "First chunk.", "score": 0.9},
            {"chunk": "Second chunk.", "score": 0.5},
        ]
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(return_value=make_stream_mock(make_staan_body([item])))

        results = await provider.search(mock_client, "q")

        assert results[0].content == "First chunk.\n\nSecond chunk."

    async def test_content_capped_at_max_chars(self, monkeypatch):
        monkeypatch.setattr(settings, "staan_content_max_chars", 10)
        item = full_result(full_content={"text": "X" * 100, "format": "markdown", "length": 100})
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(return_value=make_stream_mock(make_staan_body([item])))

        results = await provider.search(mock_client, "q")

        assert results[0].content == "X" * 10

    async def test_content_stripped_beyond_max_results(self, monkeypatch):
        monkeypatch.setattr(settings, "staan_content_max_results", 2)
        items = [full_result(url=f"https://example.com/{i}") for i in range(4)]
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(return_value=make_stream_mock(make_staan_body(items)))

        results = await provider.search(mock_client, "q")

        assert len(results) == 4
        assert results[0].content is not None
        assert results[1].content is not None
        assert results[2].content is None
        assert results[3].content is None

    async def test_filters_invalid_urls(self):
        items = [
            full_result(),
            full_result(url="javascript:alert(1)"),
            full_result(url=""),
            full_result(title=""),
        ]
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(return_value=make_stream_mock(make_staan_body(items)))

        results = await provider.search(mock_client, "q")

        assert len(results) == 1
        assert results[0].url == "https://example.com/vector-dbs"

    async def test_http_error_returns_empty(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(side_effect=httpx.ConnectError("Connection failed"))

        assert await provider.search(mock_client, "q") == []

    async def test_sends_bearer_auth_and_timeout(self, monkeypatch):
        monkeypatch.setattr(settings, "staan_api_key", "test-staan-key")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(return_value=make_stream_mock(make_staan_body([])))

        await provider.search(mock_client, "q")

        kwargs = mock_client.stream.call_args.kwargs
        assert kwargs["headers"]["Authorization"] == "Bearer test-staan-key"
        assert kwargs["timeout"] == settings.staan_timeout
        assert mock_client.stream.call_args.args == (
            "GET",
            f"{settings.staan_url}/v2/search/web",
        )


class TestStaanCaching:
    @pytest.fixture
    def in_memory_backend(self):
        backend = InMemoryBackend()
        set_backend_for_testing(backend)
        yield backend
        set_backend_for_testing(None)

    async def test_search_caches_and_reuses(self, in_memory_backend):
        body = make_staan_body([full_result()])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(side_effect=lambda *a, **kw: make_stream_mock(body))

        r1 = await provider.search(mock_client, "hello")
        r2 = await provider.search(mock_client, "hello")

        assert mock_client.stream.call_count == 1  # second call hit cache
        assert r1[0].url == r2[0].url
        assert r1[0].content == r2[0].content

    async def test_market_change_is_a_cache_miss(self, in_memory_backend, monkeypatch):
        body = make_staan_body([full_result()])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(side_effect=lambda *a, **kw: make_stream_mock(body))

        monkeypatch.setattr(settings, "staan_market", "en-us")
        await provider.search(mock_client, "hello")
        monkeypatch.setattr(settings, "staan_market", "da-dk")
        await provider.search(mock_client, "hello")

        assert mock_client.stream.call_count == 2

    async def test_empty_results_not_cached(self, in_memory_backend):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream = MagicMock(
            side_effect=lambda *a, **kw: make_stream_mock(make_staan_body([]))
        )

        await provider.search(mock_client, "nothing")
        await provider.search(mock_client, "nothing")

        assert mock_client.stream.call_count == 2  # no negative caching
