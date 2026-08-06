"""Unit tests for the Met Museum API client.

All tests use mocked HTTP responses — no real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from artgents.clients.met import (
    ImageUnavailableError,
    MetClient,
    MetObject,
    _USER_AGENT,
)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

VALID_PUBLIC_DOMAIN_OBJECT = {
    "objectID": 436535,
    "title": "Wheat Field with Cypresses",
    "artistDisplayName": "Vincent van Gogh",
    "objectDate": "1889",
    "medium": "Oil on canvas",
    "department": "European Paintings",
    "isPublicDomain": True,
    "primaryImage": "https://images.metmuseum.org/CRDImages/ep/original/DP-42549-001.jpg",
    "primaryImageSmall": "https://images.metmuseum.org/CRDImages/ep/web-large/DP-42549-001.jpg",
}

NON_PUBLIC_DOMAIN_OBJECT = {
    "objectID": 12345,
    "title": "Some Restricted Work",
    "artistDisplayName": "Modern Artist",
    "objectDate": "2005",
    "medium": "Acrylic on canvas",
    "department": "Modern Art",
    "isPublicDomain": False,
    "primaryImage": "",
    "primaryImageSmall": "",
}

PUBLIC_DOMAIN_EMPTY_IMAGE_OBJECT = {
    "objectID": 67890,
    "title": "Ancient Artifact",
    "artistDisplayName": "",
    "objectDate": "300 BCE",
    "medium": "Bronze",
    "department": "Greek and Roman Art",
    "isPublicDomain": True,
    "primaryImage": "",
    "primaryImageSmall": "",
}


# ---------------------------------------------------------------------------
# MetObject model tests
# ---------------------------------------------------------------------------


class TestMetObjectModel:
    """Test MetObject Pydantic model parsing."""

    def test_valid_public_domain_object(self):
        """Valid public domain object parses correctly."""
        obj = MetObject.model_validate(VALID_PUBLIC_DOMAIN_OBJECT)
        assert obj.object_id == 436535
        assert obj.title == "Wheat Field with Cypresses"
        assert obj.artist_display_name == "Vincent van Gogh"
        assert obj.is_public_domain is True
        assert "DP-42549-001" in obj.primary_image
        assert "DP-42549-001" in obj.primary_image_small

    def test_non_public_domain_object(self):
        """Non-public-domain object parses (validation happens in get_object)."""
        obj = MetObject.model_validate(NON_PUBLIC_DOMAIN_OBJECT)
        assert obj.is_public_domain is False
        assert obj.primary_image == ""

    def test_empty_optional_fields_default(self):
        """Missing optional string fields default to empty string."""
        minimal = {
            "objectID": 1,
            "isPublicDomain": True,
        }
        obj = MetObject.model_validate(minimal)
        assert obj.title == ""
        assert obj.artist_display_name == ""
        assert obj.primary_image == ""


# ---------------------------------------------------------------------------
# MetClient tests (mocked HTTP)
# ---------------------------------------------------------------------------


class TestMetClient:
    """Test MetClient with mocked HTTP responses."""

    @pytest.fixture
    def mock_transport(self):
        """Create a mock transport for httpx."""
        return httpx.MockTransport(lambda req: httpx.Response(200, json={}))

    async def test_user_agent_header_set(self):
        """Client sets User-Agent header on initialization."""
        async with MetClient() as client:
            assert client._client.headers["User-Agent"] == _USER_AGENT

    async def test_get_object_success_public_domain(self):
        """Successful fetch of a public-domain object with image."""

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            assert "/objects/436535" in str(request.url)
            return httpx.Response(200, json=VALID_PUBLIC_DOMAIN_OBJECT)

        async with MetClient() as client:
            client._client = httpx.AsyncClient(
                transport=httpx.MockTransport(mock_handler),
                base_url="https://collectionapi.metmuseum.org/public/collection/v1",
            )
            obj = await client.get_object(436535)

        assert obj.object_id == 436535
        assert obj.title == "Wheat Field with Cypresses"
        assert obj.is_public_domain is True
        assert obj.primary_image != ""

    async def test_get_object_rejects_non_public_domain(self):
        """Non-public-domain object raises ImageUnavailableError."""

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=NON_PUBLIC_DOMAIN_OBJECT)

        async with MetClient() as client:
            client._client = httpx.AsyncClient(
                transport=httpx.MockTransport(mock_handler),
                base_url="https://collectionapi.metmuseum.org/public/collection/v1",
            )
            with pytest.raises(ImageUnavailableError, match="not public domain"):
                await client.get_object(12345)

    async def test_get_object_rejects_empty_primary_image(self):
        """Public-domain object with empty primaryImage raises ImageUnavailableError."""

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=PUBLIC_DOMAIN_EMPTY_IMAGE_OBJECT)

        async with MetClient() as client:
            client._client = httpx.AsyncClient(
                transport=httpx.MockTransport(mock_handler),
                base_url="https://collectionapi.metmuseum.org/public/collection/v1",
            )
            with pytest.raises(ImageUnavailableError, match="no usable image URL"):
                await client.get_object(67890)

    async def test_get_object_accepts_primary_image_small_only(self):
        """Object with only primaryImageSmall (not primaryImage) is accepted."""
        obj_data = {
            **VALID_PUBLIC_DOMAIN_OBJECT,
            "primaryImage": "",
            "primaryImageSmall": "https://images.metmuseum.org/small.jpg",
        }

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=obj_data)

        async with MetClient() as client:
            client._client = httpx.AsyncClient(
                transport=httpx.MockTransport(mock_handler),
                base_url="https://collectionapi.metmuseum.org/public/collection/v1",
            )
            obj = await client.get_object(436535)

        assert obj.primary_image_small == "https://images.metmuseum.org/small.jpg"

    async def test_get_object_http_error_propagates(self):
        """HTTP 404 from the API propagates as HTTPStatusError."""

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="Not Found")

        async with MetClient() as client:
            client._client = httpx.AsyncClient(
                transport=httpx.MockTransport(mock_handler),
                base_url="https://collectionapi.metmuseum.org/public/collection/v1",
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_object(999999)

    async def test_search_returns_object_ids(self):
        """Search returns list of object IDs."""
        search_response = {"total": 2, "objectIDs": [436535, 437133]}

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            assert "q=van+gogh" in str(request.url) or "q=van%20gogh" in str(request.url)
            return httpx.Response(200, json=search_response)

        async with MetClient() as client:
            client._client = httpx.AsyncClient(
                transport=httpx.MockTransport(mock_handler),
                base_url="https://collectionapi.metmuseum.org/public/collection/v1",
            )
            ids = await client.search("van gogh")

        assert ids == [436535, 437133]

    async def test_search_empty_results(self):
        """Search with no results returns empty list."""
        search_response = {"total": 0, "objectIDs": None}

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=search_response)

        async with MetClient() as client:
            client._client = httpx.AsyncClient(
                transport=httpx.MockTransport(mock_handler),
                base_url="https://collectionapi.metmuseum.org/public/collection/v1",
            )
            ids = await client.search("nonexistent artwork xyz")

        assert ids == []
