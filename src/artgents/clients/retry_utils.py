"""Shared retry/backoff utility for httpx-based API clients.

Provides exponential backoff for transient errors (429, connection
failures, timeouts) — the same pattern proven on the Vertex client,
extracted into a reusable helper for Wikidata, Met, AIC, and Parallel.
"""

from __future__ import annotations

import asyncio
from typing import TypeVar

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# Configuration — same values as Vertex's proven retry logic
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
INITIAL_DELAY_S = 2.0

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Retryable error classification
# ---------------------------------------------------------------------------


def _is_retryable_response(response: httpx.Response) -> bool:
    """Check if an HTTP response is a transient error worth retrying."""
    return response.status_code == 429


def _is_retryable_exception(exc: Exception) -> bool:
    """Check if an exception is a transient network error worth retrying."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                        httpx.PoolTimeout, httpx.ConnectTimeout)):
        return True
    # Catch generic timeout/connection text in unknown exceptions
    exc_str = str(exc).lower()
    if "timed out" in exc_str or "timeout" in exc_str:
        return True
    if "connection" in exc_str and ("reset" in exc_str or "closed" in exc_str or "refused" in exc_str):
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def httpx_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    raise_for_status: bool = True,
    **kwargs,
) -> httpx.Response:
    """Make an httpx request with retry/backoff on transient errors.

    Wraps client.request() with up to 3 retries on 429 status or
    connection/timeout errors. Non-transient errors fail immediately.

    Args:
        client: The httpx.AsyncClient to use.
        method: HTTP method ("GET", "POST", etc.).
        url: Request URL (can be relative if client has base_url).
        raise_for_status: If True (default), calls response.raise_for_status()
            after a successful (non-retried) response.
        **kwargs: Additional arguments passed to client.request().

    Returns:
        The httpx.Response (with status already checked if raise_for_status=True).

    Raises:
        httpx.HTTPStatusError: If a non-retryable HTTP error occurs, or
            retries are exhausted on a 429.
        httpx.ConnectError, httpx.TimeoutException: If retries are exhausted
            on connection/timeout errors.
    """
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.request(method, url, **kwargs)

            # Check if we should retry this response
            if _is_retryable_response(response) and attempt < MAX_RETRIES:
                delay = INITIAL_DELAY_S * (2 ** attempt)
                logger.warning(
                    "HTTP 429 — retry {}/{} after {:.1f}s (url={})",
                    attempt + 1, MAX_RETRIES, delay, url,
                )
                await asyncio.sleep(delay)
                continue

            # Non-retryable response (or retries exhausted) — return/raise
            if raise_for_status:
                response.raise_for_status()
            return response

        except httpx.HTTPStatusError:
            # Already raised by raise_for_status on non-429 — don't retry
            raise
        except Exception as exc:
            if not _is_retryable_exception(exc):
                raise  # Non-transient: fail immediately

            last_exc = exc
            if attempt < MAX_RETRIES:
                delay = INITIAL_DELAY_S * (2 ** attempt)
                logger.warning(
                    "Transient error — retry {}/{} after {:.1f}s (type={}, error={}, url={})",
                    attempt + 1, MAX_RETRIES, delay,
                    type(exc).__name__, str(exc)[:100], url,
                )
                await asyncio.sleep(delay)
            else:
                raise  # Retries exhausted: propagate original error

    # Should not reach here, but satisfy type checker
    assert last_exc is not None
    raise last_exc
