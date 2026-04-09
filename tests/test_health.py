from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    """Create an async test client with mocked lifespan dependencies."""
    with (
        patch("search_agent.main.init_shared_clients"),
        patch("search_agent.main.close_shared_clients", new_callable=AsyncMock),
        patch("search_agent.main.mcp") as mock_mcp,
    ):
        # Make the MCP session manager a no-op async context manager
        mock_session_mgr = MagicMock()
        mock_run = MagicMock()
        mock_run.__aenter__ = AsyncMock(return_value=None)
        mock_run.__aexit__ = AsyncMock(return_value=None)
        mock_session_mgr.run.return_value = mock_run
        mock_mcp.session_manager = mock_session_mgr

        from search_agent.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


class TestHealthEndpoint:
    async def test_basic_health(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @patch("search_agent.main.get_http_client")
    async def test_deep_health_searxng_ok(self, mock_get_client, client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_http

        response = await client.get("/health?deep=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["searxng"] == "reachable"

    @patch("search_agent.main.get_http_client")
    async def test_deep_health_searxng_down(self, mock_get_client, client):
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_get_client.return_value = mock_http

        response = await client.get("/health?deep=true")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["searxng"] == "unreachable"
