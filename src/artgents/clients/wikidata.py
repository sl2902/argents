"""Wikidata SPARQL client.

Thin wrapper around raw httpx POST to query.wikidata.org/sparql,
requesting application/sparql-results+json. No SPARQLWrapper dependency.

Provides provenance-relevant queries: ownership history (P127/P195),
significant events (P793), and plunder/theft-related flags.
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

_USER_AGENT = (
    "Artgents/1.0 (https://github.com/artgents; research project) "
    "httpx/0.27"
)


class WikidataResult(BaseModel):
    """A single result row from a Wikidata SPARQL query."""

    item_url: str = Field(..., description="Wikidata entity URL")
    label: str = Field(default="", description="Entity label")
    description: str = Field(default="", description="Entity description")
    properties: dict[str, str] = Field(
        default_factory=dict,
        description="Additional property values from the query",
    )


class WikidataProvenance(BaseModel):
    """Parsed provenance-relevant data from Wikidata for an artwork."""

    entity_url: str | None = Field(
        default=None, description="Wikidata URL of the artwork entity, if found"
    )
    ownership_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of {owner, start_date, end_date, source_url} entries",
    )
    collections: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of {collection_name, source_url} entries",
    )
    significant_events: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of {event_label, date, source_url} entries (theft, restitution, etc.)",
    )


class WikidataClient:
    """Async client for Wikidata SPARQL queries.

    Applies a default LIMIT to queries that don't already have one,
    preventing unbounded queries from timing out on prolific artists.

    Usage:
        async with WikidataClient() as client:
            result = await client.query_provenance("Georges Braque", "1912")
    """

    DEFAULT_LIMIT: int = 50

    def __init__(self, *, default_limit: int = 50, timeout: float = 15.0) -> None:
        """Initialize the Wikidata client.

        Args:
            default_limit: Default LIMIT to inject into queries that don't
                already have one. Set to 0 to disable default injection.
            timeout: HTTP request timeout in seconds (default: 15s — bounded
                queries should complete well under this).
        """
        self._default_limit = default_limit
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/sparql-results+json",
            },
        )

    async def __aenter__(self) -> "WikidataClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _execute_sparql(self, query: str) -> dict[str, Any]:
        """Execute a SPARQL query and return the raw JSON response.

        If the query does not already contain a LIMIT clause and a
        default_limit is configured, one is appended automatically.

        Args:
            query: SPARQL query string.

        Returns:
            Parsed JSON response from Wikidata.

        Raises:
            httpx.HTTPStatusError: If the endpoint returns non-2xx.
        """
        query = self._ensure_limit(query)
        response = await self._client.post(
            WIKIDATA_SPARQL_ENDPOINT,
            data={"query": query},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()

    def _ensure_limit(self, query: str) -> str:
        """Inject a default LIMIT clause if the query doesn't have one.

        Does not modify queries that already contain an explicit LIMIT —
        respects intentional caller choices.
        """
        import re

        if self._default_limit <= 0:
            return query

        # Check if query already has a LIMIT clause (case-insensitive)
        if re.search(r"\bLIMIT\b", query, re.IGNORECASE):
            return query

        # Append LIMIT to the end of the query
        return f"{query.rstrip()}\nLIMIT {self._default_limit}\n"

    async def query_provenance(
        self,
        artist: str,
        creation_window: str = "",
        keywords: list[str] | None = None,
    ) -> WikidataProvenance:
        """Query Wikidata for provenance-relevant information about an artwork.

        Searches for artworks by the given artist and retrieves:
        - Ownership history (P127 owned by / P195 collection)
        - Significant events (P793) — theft, restitution, confiscation
        - Plunder-related properties

        Args:
            artist: Artist name or attribution string.
            creation_window: Approximate creation period (e.g. "1912").
            keywords: Additional search keywords for narrowing.

        Returns:
            WikidataProvenance with all retrieved provenance data.
        """
        # Clean artist attribution phrasing for search
        search_artist = artist
        for prefix in ["Attributed to ", "Manner of ", "Circle of ", "School of "]:
            if search_artist.startswith(prefix):
                search_artist = search_artist[len(prefix):]
                break

        # Build SPARQL query targeting provenance properties
        sparql = self._build_provenance_query(search_artist, creation_window)
        try:
            data = await self._execute_sparql(sparql)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Wikidata SPARQL query failed: status={}, artist={}",
                exc.response.status_code,
                artist,
            )
            raise

        return self._parse_provenance_response(data)

    def _build_provenance_query(self, artist: str, creation_window: str) -> str:
        """Build a SPARQL query for provenance-relevant properties."""
        # Escape quotes in artist name for SPARQL
        escaped_artist = artist.replace('"', '\\"')

        query = f"""
        SELECT DISTINCT ?item ?itemLabel ?itemDescription
               ?owner ?ownerLabel ?startTime ?endTime
               ?collection ?collectionLabel
               ?event ?eventLabel ?eventDate
        WHERE {{
          # Find the artist entity
          ?artist rdfs:label "{escaped_artist}"@en .
          ?artist wdt:P106 wd:Q1028181 .  # occupation: painter (or similar)

          # Find artworks by this artist
          ?item wdt:P170 ?artist .  # creator
          ?item wdt:P31/wdt:P279* wd:Q3305213 .  # instance of: painting (or subclass)

          # Optional: ownership history (P127)
          OPTIONAL {{
            ?item p:P127 ?ownerStatement .
            ?ownerStatement ps:P127 ?owner .
            OPTIONAL {{ ?ownerStatement pq:P580 ?startTime . }}
            OPTIONAL {{ ?ownerStatement pq:P582 ?endTime . }}
          }}

          # Optional: collection (P195)
          OPTIONAL {{
            ?item wdt:P195 ?collection .
          }}

          # Optional: significant event (P793) — theft, restitution, etc.
          OPTIONAL {{
            ?item p:P793 ?eventStatement .
            ?eventStatement ps:P793 ?event .
            OPTIONAL {{ ?eventStatement pq:P585 ?eventDate . }}
          }}

          SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "en" .
          }}
        }}
        """
        return query

    def _parse_provenance_response(
        self, data: dict[str, Any]
    ) -> WikidataProvenance:
        """Parse SPARQL JSON results into WikidataProvenance."""
        bindings = data.get("results", {}).get("bindings", [])

        if not bindings:
            return WikidataProvenance()

        entity_url: str | None = None
        ownership_history: list[dict[str, str]] = []
        collections: list[dict[str, str]] = []
        significant_events: list[dict[str, str]] = []
        seen_owners: set[str] = set()
        seen_collections: set[str] = set()
        seen_events: set[str] = set()

        for binding in bindings:
            # Get entity URL from first result
            if entity_url is None and "item" in binding:
                raw_url = binding["item"]["value"]
                # Validate the URL looks like a proper Wikidata entity URI
                if raw_url.startswith("http://www.wikidata.org/entity/Q") or \
                   raw_url.startswith("https://www.wikidata.org/entity/Q"):
                    entity_url = raw_url
                else:
                    logger.warning(
                        "Unexpected Wikidata entity URI format: {}", raw_url
                    )

            # Parse ownership
            if "owner" in binding:
                owner_label = binding.get("ownerLabel", {}).get("value", "")
                owner_key = owner_label + binding.get("startTime", {}).get("value", "")
                if owner_key and owner_key not in seen_owners:
                    seen_owners.add(owner_key)
                    entry = {
                        "owner": owner_label,
                        "source_url": entity_url or "",
                    }
                    if "startTime" in binding:
                        entry["start_date"] = binding["startTime"]["value"][:10]
                    if "endTime" in binding:
                        entry["end_date"] = binding["endTime"]["value"][:10]
                    ownership_history.append(entry)

            # Parse collections
            if "collection" in binding:
                coll_label = binding.get("collectionLabel", {}).get("value", "")
                if coll_label and coll_label not in seen_collections:
                    seen_collections.add(coll_label)
                    collections.append({
                        "collection_name": coll_label,
                        "source_url": entity_url or "",
                    })

            # Parse significant events
            if "event" in binding:
                event_label = binding.get("eventLabel", {}).get("value", "")
                if event_label and event_label not in seen_events:
                    seen_events.add(event_label)
                    entry = {
                        "event_label": event_label,
                        "source_url": entity_url or "",
                    }
                    if "eventDate" in binding:
                        entry["date"] = binding["eventDate"]["value"][:10]
                    significant_events.append(entry)

        return WikidataProvenance(
            entity_url=entity_url,
            ownership_history=ownership_history,
            collections=collections,
            significant_events=significant_events,
        )
