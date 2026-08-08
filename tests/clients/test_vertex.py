"""Unit tests for the Vertex AI client configuration.

Focuses on timeout configuration correctness — ensures the timeout values
passed to the underlying httpx client are in the right units and all
sub-timeouts have non-trivial values.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from artgents.clients.vertex import _build_client, reset_client


# ---------------------------------------------------------------------------
# Timeout configuration correctness
# ---------------------------------------------------------------------------


class TestTimeoutConfiguration:
    """Verify timeout is correctly configured in seconds (not milliseconds).

    The google-genai HttpOptions.timeout field is in MILLISECONDS, and the
    library divides by 1000 before passing to httpx. A previous bug set
    timeout=120 (120ms) instead of timeout=120_000 (120s), causing
    WriteTimeout errors at ~271ms for image-bearing requests.
    """

    @patch("artgents.clients.vertex.settings")
    def test_http_options_timeout_is_in_correct_millisecond_unit(
        self, mock_settings
    ):
        """HttpOptions.timeout should be >= 30_000ms (30s) to avoid spurious timeouts."""
        mock_settings.gcp_project = "test-project"
        mock_settings.gcp_location = "us-central1"

        client = _build_client()
        http_options = client._api_client._http_options

        # timeout is in milliseconds; must be at least 30_000 (30s)
        # to avoid spurious WriteTimeout on image payloads
        assert http_options.timeout is not None
        assert http_options.timeout >= 30_000, (
            f"HttpOptions.timeout={http_options.timeout}ms is too low. "
            f"This is in MILLISECONDS — values < 30_000 will cause "
            f"WriteTimeout errors for image-bearing requests."
        )

    @patch("artgents.clients.vertex.settings")
    def test_async_client_has_granular_sub_timeouts(self, mock_settings):
        """The async httpx client should have all four sub-timeouts set to non-trivial values.

        Prevents regressions where connect/write/read/pool timeouts are
        accidentally left at a trivially small value.
        """
        mock_settings.gcp_project = "test-project"
        mock_settings.gcp_location = "us-central1"

        client = _build_client()

        # Access the underlying async httpx client's timeout configuration
        async_client = client._api_client._async_httpx_client
        timeout = async_client.timeout

        assert isinstance(timeout, httpx.Timeout)

        # All four sub-timeouts must be non-None and > 5 seconds
        assert timeout.connect is not None and timeout.connect >= 5.0, (
            f"connect timeout={timeout.connect}s is too low"
        )
        assert timeout.write is not None and timeout.write >= 5.0, (
            f"write timeout={timeout.write}s is too low"
        )
        assert timeout.read is not None and timeout.read >= 30.0, (
            f"read timeout={timeout.read}s is too low (model generation needs 30s+)"
        )
        assert timeout.pool is not None and timeout.pool >= 5.0, (
            f"pool timeout={timeout.pool}s is too low"
        )

    @patch("artgents.clients.vertex.settings")
    def test_timeout_values_are_as_expected(self, mock_settings):
        """Verify the specific timeout values match the documented configuration."""
        mock_settings.gcp_project = "test-project"
        mock_settings.gcp_location = "us-central1"

        client = _build_client()
        async_client = client._api_client._async_httpx_client
        timeout = async_client.timeout

        # Expected values from the client configuration
        assert timeout.connect == 10.0
        assert timeout.write == 30.0
        assert timeout.read == 120.0
        assert timeout.pool == 10.0

    @patch("artgents.clients.vertex.settings")
    def test_per_request_timeout_in_seconds_is_correct(self, mock_settings):
        """The per-request timeout (derived from HttpOptions) should be 120 seconds.

        HttpOptions.timeout is in ms; the library divides by 1000 for httpx.
        """
        mock_settings.gcp_project = "test-project"
        mock_settings.gcp_location = "us-central1"

        client = _build_client()
        http_options = client._api_client._http_options

        # 120_000ms / 1000 = 120.0 seconds per-request timeout
        expected_seconds = http_options.timeout / 1000.0
        assert expected_seconds == 120.0
