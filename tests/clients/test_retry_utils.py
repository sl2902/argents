"""Unit tests for the shared retry/backoff utility."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from artgents.clients.retry_utils import httpx_request_with_retry


# ---------------------------------------------------------------------------
# retry_utils.py — direct tests
# ---------------------------------------------------------------------------


class TestHttpxRequestWithRetry:
    """Tests for httpx_request_with_retry."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock httpx.AsyncClient."""
        client = AsyncMock(spec=httpx.AsyncClient)
        return client

    async def test_success_on_first_try(self, mock_client):
        """Successful response on first attempt — no retries."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()
        mock_client.request.return_value = response

        result = await httpx_request_with_retry(mock_client, "GET", "/test")

        assert result == response
        assert mock_client.request.call_count == 1

    async def test_retries_on_429_then_succeeds(self, mock_client):
        """429 on first two attempts, success on third — retries work."""
        response_429 = MagicMock(spec=httpx.Response)
        response_429.status_code = 429

        response_200 = MagicMock(spec=httpx.Response)
        response_200.status_code = 200
        response_200.raise_for_status = MagicMock()

        mock_client.request.side_effect = [response_429, response_429, response_200]

        with patch("artgents.clients.retry_utils.asyncio.sleep", new_callable=AsyncMock):
            result = await httpx_request_with_retry(mock_client, "GET", "/test")

        assert result == response_200
        assert mock_client.request.call_count == 3

    async def test_non_retryable_error_fails_immediately(self, mock_client):
        """Non-retryable HTTP error (e.g. 404) fails on first attempt."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 404
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=response
        )
        mock_client.request.return_value = response

        with pytest.raises(httpx.HTTPStatusError):
            await httpx_request_with_retry(mock_client, "GET", "/test")

        # Only one attempt — no retries
        assert mock_client.request.call_count == 1

    async def test_retries_exhausted_raises_original_error(self, mock_client):
        """429 on all attempts — raises after retries exhausted."""
        response_429 = MagicMock(spec=httpx.Response)
        response_429.status_code = 429
        response_429.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate Limited", request=MagicMock(), response=response_429
        )

        mock_client.request.return_value = response_429

        with patch("artgents.clients.retry_utils.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.HTTPStatusError):
                await httpx_request_with_retry(mock_client, "GET", "/test")

        # 1 initial + 3 retries = 4 total
        assert mock_client.request.call_count == 4

    async def test_retries_on_connection_error(self, mock_client):
        """Connection error retries then succeeds."""
        response_200 = MagicMock(spec=httpx.Response)
        response_200.status_code = 200
        response_200.raise_for_status = MagicMock()

        mock_client.request.side_effect = [
            httpx.ConnectError("Connection refused"),
            response_200,
        ]

        with patch("artgents.clients.retry_utils.asyncio.sleep", new_callable=AsyncMock):
            result = await httpx_request_with_retry(mock_client, "GET", "/test")

        assert result == response_200
        assert mock_client.request.call_count == 2

    async def test_retries_on_timeout(self, mock_client):
        """Timeout error retries then succeeds."""
        response_200 = MagicMock(spec=httpx.Response)
        response_200.status_code = 200
        response_200.raise_for_status = MagicMock()

        mock_client.request.side_effect = [
            httpx.ReadTimeout("Timed out"),
            response_200,
        ]

        with patch("artgents.clients.retry_utils.asyncio.sleep", new_callable=AsyncMock):
            result = await httpx_request_with_retry(mock_client, "GET", "/test")

        assert result == response_200
        assert mock_client.request.call_count == 2


# ---------------------------------------------------------------------------
# Client integration tests — confirm each client uses retry
# ---------------------------------------------------------------------------


class TestWikidataRetryIntegration:
    """Confirm Wikidata client retries on 429."""

    async def test_wikidata_retries_on_429(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        from artgents.clients.wikidata import WikidataClient

        client = WikidataClient()

        response_429 = MagicMock(spec=httpx.Response)
        response_429.status_code = 429

        response_200 = MagicMock(spec=httpx.Response)
        response_200.status_code = 200
        response_200.raise_for_status = MagicMock()
        response_200.json.return_value = {"results": {"bindings": []}}

        client._client.request = AsyncMock(side_effect=[response_429, response_200])

        with patch("artgents.clients.retry_utils.asyncio.sleep", new_callable=AsyncMock):
            result = await client._execute_sparql("SELECT ?x WHERE { ?x ?y ?z } LIMIT 1")

        assert result == {"results": {"bindings": []}}
        assert client._client.request.call_count == 2


class TestMetRetryIntegration:
    """Confirm Met client retries on 429."""

    async def test_met_retries_on_429(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        from artgents.clients.met import MetClient

        client = MetClient()

        response_429 = MagicMock(spec=httpx.Response)
        response_429.status_code = 429

        response_200 = MagicMock(spec=httpx.Response)
        response_200.status_code = 200
        response_200.raise_for_status = MagicMock()
        response_200.json.return_value = {"objectID": 1, "title": "Test"}

        client._client.request = AsyncMock(side_effect=[response_429, response_200])

        with patch("artgents.clients.retry_utils.asyncio.sleep", new_callable=AsyncMock):
            result = await client.get_object_raw(1)

        assert result == {"objectID": 1, "title": "Test"}
        assert client._client.request.call_count == 2


class TestAICRetryIntegration:
    """Confirm AIC client retries on 429."""

    async def test_aic_retries_on_429(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        from artgents.clients.aic import AICClient

        client = AICClient()

        response_429 = MagicMock(spec=httpx.Response)
        response_429.status_code = 429

        response_200 = MagicMock(spec=httpx.Response)
        response_200.status_code = 200
        response_200.raise_for_status = MagicMock()
        response_200.json.return_value = {"data": []}

        client._client.request = AsyncMock(side_effect=[response_429, response_200])

        with patch("artgents.clients.retry_utils.asyncio.sleep", new_callable=AsyncMock):
            result = await client.search("test")

        assert result == []
        assert client._client.request.call_count == 2


class TestParallelRetryIntegration:
    """Confirm Parallel client retries on RateLimitError."""

    async def test_parallel_retries_on_rate_limit(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")
        monkeypatch.setenv("PARALLEL_WEB_API_KEY", "test-key")

        import parallel as parallel_sdk
        from artgents.clients.parallel import ParallelClient

        client = ParallelClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.results = []

        client._client.search = AsyncMock(
            side_effect=[
                parallel_sdk.RateLimitError(
                    "rate limited",
                    response=MagicMock(status_code=429),
                    body=None,
                ),
                mock_response,
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.search("test query")

        assert result.hits == []
        assert client._client.search.call_count == 2
