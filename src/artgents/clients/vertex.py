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
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project,
        location=settings.gcp_location,
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
        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "Vertex AI call failed after {:.0f}ms: model={}, error={}",
            elapsed_ms,
            model,
            str(exc),
        )
        raise VertexCallError(str(exc)) from exc

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("Vertex AI call completed in {:.0f}ms (model={})", elapsed_ms, model)

    # Parse the structured JSON response
    import json

    text = response.text
    if text is None:
        raise VertexCallError("Vertex AI returned empty response text")

    return json.loads(text)


class VertexCallError(Exception):
    """Raised when a Vertex AI generation call fails."""

    pass
