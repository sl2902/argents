"""Met Museum API client.

Thin wrapper over the public Met Museum Collection API (no auth required).
Handles:
- Consistent User-Agent header (required to avoid Incapsula 403s)
- isPublicDomain + primaryImage validation before returning objects
- Typed errors for unavailable images
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from artgents.clients.retry_utils import httpx_request_with_retry
from pydantic import BaseModel, Field

MET_API_BASE = "https://collectionapi.metmuseum.org/public/collection/v1"

# Realistic browser-like User-Agent — Met's Incapsula bot protection
# returns 403 without one.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


class ImageUnavailableError(Exception):
    """Raised when a Met object has no usable public-domain image.

    This covers both rights-restricted objects (isPublicDomain=false) and
    objects with empty primaryImage/primaryImageSmall fields.
    """

    pass


class MetObject(BaseModel):
    """Parsed Met Museum object with validated image availability."""

    object_id: int = Field(..., alias="objectID")
    title: str = ""
    artist_display_name: str = Field(default="", alias="artistDisplayName")
    object_date: str = Field(default="", alias="objectDate")
    medium: str = ""
    department: str = ""
    is_public_domain: bool = Field(..., alias="isPublicDomain")
    primary_image: str = Field(default="", alias="primaryImage")
    primary_image_small: str = Field(default="", alias="primaryImageSmall")

    model_config = {"populate_by_name": True}


class MetClient:
    """Async client for the Met Museum Collection API.

    Usage:
        async with MetClient() as client:
            obj = await client.get_object(436535)
            print(obj.primary_image)
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=MET_API_BASE,
            headers={"User-Agent": _USER_AGENT},
            timeout=30.0,
        )

    async def __aenter__(self) -> "MetClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def get_object_raw(self, object_id: int) -> dict[str, Any]:
        """Fetch raw JSON for a Met object by ID.

        Args:
            object_id: Met Museum object ID.

        Returns:
            Raw JSON dict from the API.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        response = await httpx_request_with_retry(
            self._client, "GET", f"/objects/{object_id}",
        )
        return response.json()

    async def get_object(self, object_id: int) -> MetObject:
        """Fetch and validate a Met object, ensuring it has a usable image.

        Args:
            object_id: Met Museum object ID.

        Returns:
            Validated MetObject with confirmed public-domain image.

        Raises:
            ImageUnavailableError: If the object is not public domain or
                has no primaryImage URL.
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        data = await self.get_object_raw(object_id)
        obj = MetObject.model_validate(data)

        if not obj.is_public_domain:
            logger.warning(
                "Met object {} is not public domain — image unavailable",
                object_id,
            )
            raise ImageUnavailableError(
                f"Met object {object_id} is not public domain "
                f"(isPublicDomain=false) — image cannot be used"
            )

        if not obj.primary_image and not obj.primary_image_small:
            logger.warning(
                "Met object {} has no primaryImage despite being public domain",
                object_id,
            )
            raise ImageUnavailableError(
                f"Met object {object_id} has no usable image URL "
                f"(primaryImage and primaryImageSmall are both empty)"
            )

        return obj

    async def search(self, query: str, *, has_images: bool = True) -> list[int]:
        """Search Met objects by keyword.

        Args:
            query: Search query string.
            has_images: If True, only return objects with images.

        Returns:
            List of object IDs matching the query.
        """
        params: dict[str, Any] = {"q": query, "hasImages": has_images}
        response = await httpx_request_with_retry(
            self._client, "GET", "/search", params=params,
        )
        data = response.json()
        return data.get("objectIDs") or []
