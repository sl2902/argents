"""Art Institute of Chicago API client.

Thin wrapper over the public AIC API (no auth required).
Follows the same pattern as met.py:
- Typed Pydantic results
- Public domain + image availability validation
- Typed error for unavailable images
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

AIC_API_BASE = "https://api.artic.edu/api/v1"
AIC_IIIF_BASE = "https://www.artic.edu/iiif/2"


class ImageUnavailableError(Exception):
    """Raised when an AIC object has no usable public-domain image."""

    pass


class AICObject(BaseModel):
    """Parsed Art Institute of Chicago artwork object."""

    id: int
    title: str = ""
    artist_display: str = ""
    date_display: str = ""
    medium_display: str = ""
    provenance_text: str = ""
    is_public_domain: bool = False
    image_id: str | None = None

    @property
    def image_url(self) -> str | None:
        """Full IIIF image URL, or None if no image_id."""
        if self.image_id:
            return f"{AIC_IIIF_BASE}/{self.image_id}/full/843,/0/default.jpg"
        return None


class AICClient:
    """Async client for the Art Institute of Chicago API.

    Usage:
        async with AICClient() as client:
            obj = await client.get_object(27992)
            print(obj.title, obj.provenance_text)
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=AIC_API_BASE,
            timeout=30.0,
        )

    async def __aenter__(self) -> "AICClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def get_object(self, object_id: int) -> AICObject:
        """Fetch and validate an AIC artwork, ensuring it has a usable image.

        Args:
            object_id: AIC artwork ID.

        Returns:
            Validated AICObject with confirmed public-domain image.

        Raises:
            ImageUnavailableError: If the object is not public domain or
                has no image_id.
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        response = await self._client.get(
            f"/artworks/{object_id}",
            params={
                "fields": "id,title,artist_display,date_display,medium_display,"
                "provenance_text,is_public_domain,image_id"
            },
        )
        response.raise_for_status()
        data = response.json().get("data", {})
        obj = AICObject.model_validate(data)

        if not obj.is_public_domain:
            logger.warning(
                "AIC object {} is not public domain — image unavailable",
                object_id,
            )
            raise ImageUnavailableError(
                f"AIC object {object_id} is not public domain "
                f"(is_public_domain=false) — image cannot be used"
            )

        if not obj.image_id:
            logger.warning(
                "AIC object {} has no image_id despite being public domain",
                object_id,
            )
            raise ImageUnavailableError(
                f"AIC object {object_id} has no usable image "
                f"(image_id is null/empty)"
            )

        return obj

    async def get_object_raw(self, object_id: int) -> AICObject:
        """Fetch an AIC artwork WITHOUT image validation.

        Useful for provenance research where the image is not needed,
        only the metadata (provenance_text, artist, dates).

        Args:
            object_id: AIC artwork ID.

        Returns:
            AICObject (may have is_public_domain=false or no image_id).

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        response = await self._client.get(
            f"/artworks/{object_id}",
            params={
                "fields": "id,title,artist_display,date_display,medium_display,"
                "provenance_text,is_public_domain,image_id"
            },
        )
        response.raise_for_status()
        data = response.json().get("data", {})
        return AICObject.model_validate(data)

    async def search(self, query: str, *, limit: int = 10) -> list[int]:
        """Search AIC artworks by keyword.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of artwork IDs matching the query.
        """
        response = await self._client.get(
            "/artworks/search",
            params={"q": query, "fields": "id", "limit": limit},
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        return [item["id"] for item in data if "id" in item]
