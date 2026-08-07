"""Shared Parallel Search client.

Thin wrapper over the Parallel Search API. Takes a query string,
returns parsed results with URLs. Does NOT contain agent-specific
query-construction logic — that lives in each agent's gather_evidence().
"""

from __future__ import annotations

from typing import Any

import parallel
from loguru import logger
from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    """A single search result from Parallel Search."""

    url: str = Field(..., description="URL of the source page")
    title: str | None = Field(default=None, description="Title of the page")
    excerpts: list[str] = Field(
        default_factory=list, description="Relevant text excerpts"
    )
    publish_date: str | None = Field(
        default=None, description="Published date if available"
    )


class ParallelSearchResult(BaseModel):
    """Parsed result from a Parallel Search query."""

    hits: list[SearchHit] = Field(default_factory=list)
    query: str = Field(..., description="The query that produced these results")


class CreditExhaustedError(Exception):
    """Raised when Parallel Search account credits are exhausted.

    This is distinct from 'no results found' — it means the search
    could not run at all due to billing limits.
    """

    pass


class ParallelClient:
    """Async client for Parallel Search API.

    Usage:
        client = ParallelClient(api_key="...")
        result = await client.search("Picasso stolen OR looted")
        for hit in result.hits:
            print(hit.url, hit.title)
    """

    def __init__(self, api_key: str) -> None:
        self._client = parallel.AsyncParallel(api_key=api_key)

    async def search(self, query: str, *, max_results: int = 3) -> ParallelSearchResult:
        """Execute a search query and return parsed results.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return (default: 3).

        Returns:
            ParallelSearchResult with hits containing URLs and excerpts.

        Raises:
            CreditExhaustedError: If the account has no remaining credits.
            parallel.APIError: For other API errors.
        """
        try:
            response = await self._client.search(
                search_queries=[query],
                advanced_settings={"max_results": max_results},
            )
        except parallel.RateLimitError as exc:
            logger.error(
                "Parallel Search credit exhausted or rate limited: {}", str(exc)
            )
            raise CreditExhaustedError(
                f"Parallel Search credits exhausted: {exc}"
            ) from exc
        except parallel.PermissionDeniedError as exc:
            logger.error(
                "Parallel Search permission denied (likely credit exhaustion): {}",
                str(exc),
            )
            raise CreditExhaustedError(
                f"Parallel Search access denied (credits exhausted?): {exc}"
            ) from exc

        hits: list[SearchHit] = []
        for result in response.results:
            hits.append(
                SearchHit(
                    url=result.url,
                    title=result.title,
                    excerpts=result.excerpts or [],
                    publish_date=result.publish_date,
                )
            )

        return ParallelSearchResult(hits=hits, query=query)

    async def close(self) -> None:
        """Close the underlying client."""
        await self._client.close()
