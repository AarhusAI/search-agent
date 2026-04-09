from unittest.mock import AsyncMock, MagicMock, patch

from search_agent.models import (
    RawSearchResult,
    SearchResult,
    Source,
)
from search_agent.pipeline import _is_simple_query


class TestSearchPipeline:
    @patch("search_agent.pipeline.analyze_synthesizer")
    @patch("search_agent.pipeline.search_multiple")
    @patch("search_agent.pipeline.query_planner")
    @patch("search_agent.pipeline.get_http_client")
    @patch("search_agent.pipeline.get_model")
    async def test_pipeline_runs_all_stages(
        self, mock_get_model, mock_get_http_client, mock_planner, mock_search, mock_analyze_synth
    ):
        from search_agent.pipeline import run_search_pipeline

        mock_get_model.return_value = MagicMock()
        mock_get_http_client.return_value = MagicMock()

        # Mock planner output
        planner_result = MagicMock()
        planner_result.output = ["search query 1", "search query 2"]
        mock_planner.run = AsyncMock(return_value=planner_result)

        # Mock search results
        mock_search.return_value = [
            RawSearchResult(
                title="Result 1",
                url="https://example.com",
                snippet="A snippet",
                engine="google",
            ),
        ]

        # Mock analyze+synthesize output
        analyze_synth_result = MagicMock()
        analyze_synth_result.output = SearchResult(
            summary="Here is the answer [1].",
            sources=[Source(title="Example", url="https://example.com")],
        )
        mock_analyze_synth.run = AsyncMock(return_value=analyze_synth_result)

        result = await run_search_pipeline(
            "compare python vs rust for web development", "some context"
        )

        assert result.summary == "Here is the answer [1]."
        assert len(result.sources) == 1
        assert result.sources[0].url == "https://example.com"

        mock_planner.run.assert_called_once()
        mock_search.assert_called_once()
        mock_analyze_synth.run.assert_called_once()

    @patch("search_agent.pipeline.search_multiple")
    @patch("search_agent.pipeline.query_planner")
    @patch("search_agent.pipeline.get_http_client")
    @patch("search_agent.pipeline.get_model")
    async def test_pipeline_empty_results(
        self, mock_get_model, mock_get_http_client, mock_planner, mock_search
    ):
        from search_agent.pipeline import run_search_pipeline

        mock_get_model.return_value = MagicMock()
        mock_get_http_client.return_value = MagicMock()

        planner_result = MagicMock()
        planner_result.output = ["search query"]
        mock_planner.run = AsyncMock(return_value=planner_result)

        mock_search.return_value = []

        result = await run_search_pipeline("compare apples vs oranges")

        assert result.summary == "No search results found."
        assert result.sources == []

    @patch("search_agent.pipeline.analyze_synthesizer")
    @patch("search_agent.pipeline.search_multiple")
    @patch("search_agent.pipeline.settings")
    @patch("search_agent.pipeline.get_http_client")
    @patch("search_agent.pipeline.get_model")
    async def test_pipeline_skips_planner_for_simple_query(
        self, mock_get_model, mock_get_http_client, mock_settings, mock_search, mock_analyze_synth
    ):
        from search_agent.pipeline import run_search_pipeline

        mock_get_model.return_value = MagicMock()
        mock_get_http_client.return_value = MagicMock()
        mock_settings.search_skip_planner_for_simple_queries = True
        mock_settings.search_pipeline_timeout = 90
        mock_settings.datetime_timezone = "UTC"
        mock_settings.datetime_format = "%Y-%m-%d"

        mock_search.return_value = [
            RawSearchResult(
                title="Result 1",
                url="https://example.com",
                snippet="Population info",
                engine="google",
            ),
        ]

        analyze_synth_result = MagicMock()
        analyze_synth_result.output = SearchResult(
            summary="The answer [1].",
            sources=[Source(title="Example", url="https://example.com")],
        )
        mock_analyze_synth.run = AsyncMock(return_value=analyze_synth_result)

        result = await run_search_pipeline("What is the population of Denmark?")

        assert result.summary == "The answer [1]."
        # Planner should not have been called — search_multiple gets the raw query
        mock_search.assert_called_once_with(
            mock_get_http_client.return_value, ["What is the population of Denmark?"]
        )


class TestIsSimpleQuery:
    def test_short_simple_query(self):
        assert _is_simple_query("What is the weather today?") is True

    def test_long_query_not_simple(self):
        query = (
            "Tell me about the history of artificial intelligence and how it"
            " relates to modern computing and what the future holds for"
            " machine learning applications in healthcare"
        )
        assert _is_simple_query(query) is False

    def test_compare_query_not_simple(self):
        assert _is_simple_query("compare Python vs Rust") is False

    def test_difference_query_not_simple(self):
        assert _is_simple_query("difference between TCP and UDP") is False

    def test_pros_and_cons_not_simple(self):
        assert _is_simple_query("pros and cons of microservices") is False

    def test_multiple_questions_not_simple(self):
        assert _is_simple_query("What is Python? What is Rust?") is False

    def test_single_word_query_simple(self):
        assert _is_simple_query("Denmark") is True

    def test_versus_not_simple(self):
        assert _is_simple_query("React versus Vue for frontend") is False


class TestSearchPipelineRaw:
    @patch("search_agent.pipeline.search_multiple")
    @patch("search_agent.pipeline.query_planner")
    @patch("search_agent.pipeline.get_http_client")
    @patch("search_agent.pipeline.get_model")
    async def test_raw_pipeline_returns_raw_results(
        self, mock_get_model, mock_get_http_client, mock_planner, mock_search
    ):
        from search_agent.pipeline import run_search_pipeline_raw

        mock_get_model.return_value = MagicMock()
        mock_get_http_client.return_value = MagicMock()

        planner_result = MagicMock()
        planner_result.output = ["search query"]
        mock_planner.run = AsyncMock(return_value=planner_result)

        expected = [
            RawSearchResult(
                title="Result 1", url="https://a.com", snippet="Snippet 1", engine="google"
            ),
            RawSearchResult(
                title="Result 2", url="https://b.com", snippet="Snippet 2", engine="bing"
            ),
        ]
        mock_search.return_value = expected

        result = await run_search_pipeline_raw("test query")

        assert result == expected

    @patch("search_agent.pipeline.search_multiple")
    @patch("search_agent.pipeline.query_planner")
    @patch("search_agent.pipeline.get_http_client")
    @patch("search_agent.pipeline.get_model")
    async def test_raw_pipeline_empty_results(
        self, mock_get_model, mock_get_http_client, mock_planner, mock_search
    ):
        from search_agent.pipeline import run_search_pipeline_raw

        mock_get_model.return_value = MagicMock()
        mock_get_http_client.return_value = MagicMock()

        planner_result = MagicMock()
        planner_result.output = ["query"]
        mock_planner.run = AsyncMock(return_value=planner_result)
        mock_search.return_value = []

        result = await run_search_pipeline_raw("empty query")

        assert result == []

    @patch("search_agent.pipeline.search_multiple")
    @patch("search_agent.pipeline.query_planner")
    @patch("search_agent.pipeline.get_http_client")
    @patch("search_agent.pipeline.get_model")
    async def test_raw_pipeline_caps_at_15(
        self, mock_get_model, mock_get_http_client, mock_planner, mock_search
    ):
        from search_agent.pipeline import run_search_pipeline_raw

        mock_get_model.return_value = MagicMock()
        mock_get_http_client.return_value = MagicMock()

        planner_result = MagicMock()
        planner_result.output = ["query"]
        mock_planner.run = AsyncMock(return_value=planner_result)
        mock_search.return_value = [
            RawSearchResult(
                title=f"R{i}", url=f"https://{i}.com", snippet=f"S{i}", engine="google"
            )
            for i in range(20)
        ]

        result = await run_search_pipeline_raw("big query")

        assert len(result) == 15
