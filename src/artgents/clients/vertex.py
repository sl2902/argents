"""Shared Vertex AI client for Artgents agents.

Wraps the google-genai library configured for Vertex AI (project-based,
not the AI Studio Gemini Developer API). Provides a multimodal generation
helper with schema-constrained structured output.
"""

from __future__ import annotations

import base64
import time
from typing import Any

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel

from artgents.config import settings


def _build_client() -> genai.Client:
    """Create a Vertex AI-backed genai client using project settings."""
    import httpx

    return genai.Client(
        vertexai=True,
        project=settings.gcp_project,
        location=settings.gcp_location,
        http_options=types.HttpOptions(
            # ── Timeout configuration ──────────────────────────────────────
            # IMPORTANT: HttpOptions.timeout is in MILLISECONDS (not seconds).
            # The google-genai library divides by 1000 before passing to httpx.
            # This value becomes a uniform per-request timeout for all httpx
            # sub-timeouts (connect, write, read, pool).
            #
            # We set 120_000ms = 120s because:
            #   • read: model generation routinely takes 40-60s; 120s prevents
            #     premature disconnects on complex prompts.
            #   • write: Visual Art Historian sends base64 image payloads that
            #     can be several MB; needs >> 1s on any real connection.
            #   • connect/pool: 120s is generous but harmless; these complete
            #     quickly in practice.
            #
            # Previous value was `timeout=120` which was only 120ms (0.12s),
            # causing WriteTimeout errors at ~271ms for image-bearing requests.
            timeout=120_000,
            # Granular sub-timeouts as a client-level default on the underlying
            # httpx.AsyncClient. The per-request timeout above (120s uniform)
            # takes precedence for normal calls, but these serve as:
            #   1. Documentation of intended per-phase budgets
            #   2. Fallback if the library ever changes per-request behavior
            # Values chosen:
            #   connect=10s  — TCP+TLS handshake; 10s covers slow DNS/routes
            #   write=30s    — sending request body (base64 images ≈ 1-5 MB)
            #   read=120s    — waiting for model response (the slow part)
            #   pool=10s     — waiting for a connection from the pool
            async_client_args={
                "timeout": httpx.Timeout(
                    connect=10.0, write=30.0, read=120.0, pool=10.0
                )
            },
        ),
    )


# Module-level lazy singleton — created on first use.
_client: genai.Client | None = None
_client_loop_id: int | None = None


def get_client() -> genai.Client:
    """Return the shared Vertex AI client (lazy-initialized singleton).

    Recreates the client if the current event loop differs from the one
    the client was created in (prevents 'Event loop is closed' errors
    when running under pytest-asyncio or similar frameworks that create
    fresh loops).
    """
    import asyncio

    global _client, _client_loop_id

    # Detect if the event loop has changed since the client was created
    try:
        current_loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        current_loop_id = None

    if _client is not None and current_loop_id != _client_loop_id:
        logger.debug("Event loop changed — recreating Vertex AI client")
        _client = None

    if _client is None:
        _client = _build_client()
        _client_loop_id = current_loop_id
        logger.info(
            "Vertex AI client initialized (project={}, location={})",
            settings.gcp_project,
            settings.gcp_location,
        )
    return _client


def reset_client() -> None:
    """Reset the singleton client (useful for testing)."""
    global _client, _client_loop_id
    _client = None
    _client_loop_id = None


def image_part_from_base64(data: str, mime_type: str = "image/jpeg") -> types.Part:
    """Create a genai Part from base64-encoded image bytes.

    Args:
        data: Base64-encoded image string.
        mime_type: MIME type of the image (default: image/jpeg).

    Returns:
        A Part with inline_data suitable for multimodal generation.
    """
    raw_bytes = base64.b64decode(data)
    return types.Part(inline_data=types.Blob(data=raw_bytes, mime_type=mime_type))


# ---------------------------------------------------------------------------
# Retry logic for 429 RESOURCE_EXHAUSTED
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_INITIAL_DELAY_S = 2.0


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is a transient error worth retrying.

    Retryable errors:
    - 429 RESOURCE_EXHAUSTED (rate limit / quota burst)
    - Server disconnects / connection resets (transient network issues)

    Non-retryable (fail immediately):
    - Auth errors, malformed requests, model errors, etc.
    """
    exc_str = str(exc).lower()
    # 429 rate limit
    if "429" in exc_str and "resource_exhausted" in exc_str:
        return True
    # Server disconnects / connection-level failures
    if "disconnected" in exc_str:
        return True
    if "connection" in exc_str and ("reset" in exc_str or "closed" in exc_str or "refused" in exc_str):
        return True
    if "timed out" in exc_str or "timeout" in exc_str:
        return True
    return False


async def _call_with_retry(client, model, contents, config):
    """Call Vertex AI with retry for transient errors (429, disconnects).

    Retries up to 3 times with exponential backoff (2s, 4s, 8s).
    Non-transient errors fail immediately without retry.
    """
    import asyncio as _asyncio

    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await client.aio.models.generate_content(
                model=model, contents=contents, config=config,
            )
        except Exception as exc:
            if not _is_retryable(exc):
                raise  # non-transient: fail immediately
            if attempt < _MAX_RETRIES:
                delay = _INITIAL_DELAY_S * (2 ** attempt)
                logger.warning(
                    "Vertex AI transient error — retry {}/{} after {:.1f}s (type={}, error: {})",
                    attempt + 1, _MAX_RETRIES, delay, type(exc).__name__, str(exc)[:100] or repr(exc)[:100],
                )
                await _asyncio.sleep(delay)
            else:
                raise  # retries exhausted


async def generate_structured(
    *,
    model: str,
    prompt: str,
    image_parts: list[types.Part],
    response_schema: type[BaseModel],
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """Call Gemini via Vertex AI with multimodal input and structured output.

    Args:
        model: Model name (e.g. "gemini-2.5-flash").
        prompt: Text prompt to send alongside images.
        image_parts: List of image Part objects (from image_part_from_base64).
        response_schema: Pydantic model class used as the JSON schema constraint
            for the model's response.
        temperature: Sampling temperature (0.0–2.0). If None, uses model default.
        max_output_tokens: Maximum tokens in the response. If None, uses model default.

    Returns:
        Parsed JSON dict matching the response_schema structure.

    Raises:
        VertexCallError: If the Vertex AI call fails.
    """
    client = get_client()

    contents: list[types.Part] = [*image_parts, types.Part(text=prompt)]

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    start = time.perf_counter()
    try:
        response = await _call_with_retry(client, model, contents, config)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Use repr() as fallback — some google-genai exceptions have empty str()
        exc_msg = str(exc) or repr(exc)
        logger.error(
            "Vertex AI call failed after {:.0f}ms: model={}, error_type={}, error={}",
            elapsed_ms,
            model,
            type(exc).__name__,
            exc_msg,
        )
        raise VertexCallError(exc_msg or f"Unknown {type(exc).__name__} error") from exc

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("Vertex AI call completed in {:.0f}ms (model={})", elapsed_ms, model)

    # Parse the structured JSON response
    import json

    text = response.text
    if text is None:
        raise VertexCallError("Vertex AI returned empty response text")

    # Check for truncation (MAX_TOKENS finish reason)
    if response.candidates:
        finish_reason = response.candidates[0].finish_reason
        if finish_reason and "MAX_TOKENS" in str(finish_reason):
            logger.warning(
                "Vertex AI response truncated (MAX_TOKENS): model={}, "
                "max_output_tokens={}. Response may be invalid JSON.",
                model,
                max_output_tokens,
            )

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error(
            "Vertex AI returned invalid JSON (likely truncated): "
            "model={}, max_output_tokens={}, response_length={}, error={}",
            model,
            max_output_tokens,
            len(text),
            str(exc),
        )
        raise VertexCallError(
            f"Vertex AI response is not valid JSON (likely truncated at "
            f"max_output_tokens={max_output_tokens}). "
            f"Response length: {len(text)} chars. Error: {exc}"
        ) from exc


class VertexCallError(Exception):
    """Raised when a Vertex AI generation call fails."""

    pass
