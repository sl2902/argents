"""Unit tests for Wikidata client query construction.

Verifies that the SPARQL query differs meaningfully based on artist input.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from artgents.clients.wikidata import WikidataClient


class TestWikidataQueryConstruction:
    """Test that SPARQL query construction is artist-driven."""

    def test_real_artist_appears_in_query(self):
        """A real artist name is embedded in the SPARQL query."""
        client = WikidataClient()
        query = client._build_provenance_query("Vincent van Gogh", "1889")
        assert '"Vincent van Gogh"@en' in query
        assert "wdt:P170" in query  # creator property
        assert "wdt:P106" in query  # occupation property

    def test_unknown_artist_produces_different_query(self):
        """'Unknown' produces a structurally different query target than a real name."""
        client = WikidataClient()
        query_real = client._build_provenance_query("Vincent van Gogh", "1889")
        query_unknown = client._build_provenance_query("Unknown", "")

        # The queries should differ in the artist label
        assert '"Vincent van Gogh"@en' in query_real
        assert '"Unknown"@en' in query_unknown
        assert '"Vincent van Gogh"@en' not in query_unknown

    def test_attribution_prefix_stripped_before_query(self):
        """Attribution prefixes are stripped so the raw name is searched."""
        client = WikidataClient()

        # Simulate what query_provenance does before calling _build_provenance_query
        test_cases = [
            ("Attributed to Georges Braque", "Georges Braque"),
            ("Manner of Rembrandt", "Rembrandt"),
            ("Circle of Rubens", "Rubens"),
            ("School of Raphael", "Raphael"),
            ("Vincent van Gogh", "Vincent van Gogh"),  # no prefix, unchanged
        ]

        for input_attr, expected_search in test_cases:
            # Replicate the prefix-stripping logic from query_provenance
            search_artist = input_attr
            for prefix in ["Attributed to ", "Manner of ", "Circle of ", "School of "]:
                if search_artist.startswith(prefix):
                    search_artist = search_artist[len(prefix):]
                    break

            assert search_artist == expected_search, (
                f"Input '{input_attr}' should produce '{expected_search}', "
                f"got '{search_artist}'"
            )

            query = client._build_provenance_query(search_artist, "")
            assert f'"{expected_search}"@en' in query

    def test_query_targets_paintings_by_artist(self):
        """Query structure finds paintings (Q3305213) by the artist via P170."""
        client = WikidataClient()
        query = client._build_provenance_query("Claude Monet", "1880")

        # Must find artist by label
        assert '"Claude Monet"@en' in query
        # Must link to paintings via creator (P170)
        assert "wdt:P170" in query
        # Must target paintings (or subclass)
        assert "wd:Q3305213" in query
        # Must query provenance properties
        assert "P127" in query  # owned by
        assert "P195" in query  # collection
        assert "P793" in query  # significant event

    @patch.object(WikidataClient, "_execute_sparql", new_callable=AsyncMock)
    async def test_query_provenance_passes_cleaned_artist_to_sparql(
        self, mock_execute
    ):
        """query_provenance() strips prefix and builds query with clean name."""
        mock_execute.return_value = {"results": {"bindings": []}}

        async with WikidataClient() as client:
            await client.query_provenance(
                artist="Attributed to Vincent van Gogh",
                creation_window="1889",
            )

        # Verify the SPARQL query sent contains the cleaned name
        call_args = mock_execute.call_args[0][0]  # first positional arg = query string
        assert '"Vincent van Gogh"@en' in call_args
        assert "Attributed to" not in call_args

    @patch.object(WikidataClient, "_execute_sparql", new_callable=AsyncMock)
    async def test_unknown_artist_still_executes_query(self, mock_execute):
        """'Unknown' artist still executes a query (no special fallback currently)."""
        mock_execute.return_value = {"results": {"bindings": []}}

        async with WikidataClient() as client:
            result = await client.query_provenance(
                artist="Unknown",
                creation_window="",
            )

        # Query was executed (not skipped)
        mock_execute.assert_called_once()
        # But with "Unknown" as the artist label
        call_args = mock_execute.call_args[0][0]
        assert '"Unknown"@en' in call_args
        # Result is empty (no matches expected)
        assert result.entity_url is None
        assert result.ownership_history == []


class TestRetrieveWikidataGuard:
    """Test the _retrieve_wikidata guard for non-specific artist names."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def test_is_specific_artist_real_names(self):
        """Real artist names are recognized as specific."""
        from artgents.agents.provenance_legal import _is_specific_artist

        assert _is_specific_artist("Vincent van Gogh") is True
        assert _is_specific_artist("Attributed to Georges Braque") is True
        assert _is_specific_artist("Manner of Rembrandt") is True
        assert _is_specific_artist("Claude Monet") is True

    def test_is_specific_artist_non_specific(self):
        """Non-specific placeholders are rejected."""
        from artgents.agents.provenance_legal import _is_specific_artist

        assert _is_specific_artist("Unknown") is False
        assert _is_specific_artist("Unknown artist") is False
        assert _is_specific_artist("unknown") is False
        assert _is_specific_artist("Anonymous") is False
        assert _is_specific_artist("Unidentified") is False
        assert _is_specific_artist("Unidentified artist") is False
        assert _is_specific_artist("") is False
        assert _is_specific_artist("   ") is False

    def test_is_specific_artist_attributed_unknown(self):
        """'Attributed to Unknown' is still non-specific after prefix stripping."""
        from artgents.agents.provenance_legal import _is_specific_artist

        assert _is_specific_artist("Attributed to Unknown") is False
        assert _is_specific_artist("Attributed to Unknown artist") is False

    @patch("artgents.clients.wikidata.WikidataClient.query_provenance", new_callable=AsyncMock)
    async def test_retrieve_wikidata_skips_unknown_artist(self, mock_query):
        """_retrieve_wikidata skips query entirely for 'Unknown' attribution."""
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.provenance_legal import _retrieve_wikidata

        search_keys = ProvenanceSearchKeys(
            primary_artist_attribution="Unknown",
            probable_creation_window="1900",
            style_and_movement="Impressionism",
            detected_signatures_or_marks=[],
            search_keywords=["landscape"],
        )
        facts: list = []
        sources_queried: list = []
        sources_failed: list = []

        await _retrieve_wikidata(search_keys, facts, sources_queried, sources_failed)

        # WikidataClient.query_provenance was NOT called
        mock_query.assert_not_called()
        # No facts produced (no spurious results)
        assert facts == []
        # Source is marked as queried (intentional skip, not a failure)
        assert "wikidata" in sources_queried
        assert "wikidata" not in sources_failed

    @patch("artgents.clients.wikidata.WikidataClient.query_provenance", new_callable=AsyncMock)
    async def test_retrieve_wikidata_calls_for_real_artist(self, mock_query):
        """_retrieve_wikidata does call query for a specific artist name."""
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.provenance_legal import _retrieve_wikidata
        from artgents.clients.wikidata import WikidataProvenance

        mock_query.return_value = WikidataProvenance()  # empty results

        search_keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Vincent van Gogh",
            probable_creation_window="1889",
            style_and_movement="Post-Impressionism",
            detected_signatures_or_marks=[],
            search_keywords=["van gogh"],
        )
        facts: list = []
        sources_queried: list = []
        sources_failed: list = []

        await _retrieve_wikidata(search_keys, facts, sources_queried, sources_failed)

        # WikidataClient.query_provenance WAS called
        mock_query.assert_called_once()
        assert "wikidata" in sources_queried

    @patch("artgents.clients.wikidata.WikidataClient.query_provenance", new_callable=AsyncMock)
    async def test_retrieve_wikidata_empty_result_produces_no_facts(self, mock_query):
        """When SPARQL returns zero bindings, no facts are produced."""
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.provenance_legal import _retrieve_wikidata
        from artgents.clients.wikidata import WikidataProvenance

        # Simulate: real artist name, but no results found in Wikidata
        mock_query.return_value = WikidataProvenance(
            entity_url=None,
            ownership_history=[],
            collections=[],
            significant_events=[],
        )

        search_keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Some Obscure Artist",
            probable_creation_window="1800",
            style_and_movement="Unknown",
            detected_signatures_or_marks=[],
            search_keywords=["obscure"],
        )
        facts: list = []
        sources_queried: list = []
        sources_failed: list = []

        await _retrieve_wikidata(search_keys, facts, sources_queried, sources_failed)

        # No facts attached — empty result doesn't produce spurious evidence
        assert facts == []
        assert "wikidata" in sources_queried
        assert "wikidata" not in sources_failed


    @patch("artgents.clients.wikidata.WikidataClient.query_provenance", new_callable=AsyncMock)
    async def test_all_facts_from_same_entity_have_identical_source_url(
        self, mock_query
    ):
        """All facts from one Wikidata entity must have byte-identical source_url
        equal to the correct entity URI. Regression guard for garbled URL bug
        (e.g. 'wikidata.2org' corruption)."""
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.provenance_legal import _retrieve_wikidata
        from artgents.clients.wikidata import WikidataProvenance

        EXPECTED_ENTITY_URL = "http://www.wikidata.org/entity/Q3791331"

        # Mock response: one entity with multiple provenance facts
        mock_query.return_value = WikidataProvenance(
            entity_url=EXPECTED_ENTITY_URL,
            ownership_history=[
                {
                    "owner": "Ferdinand Bloch-Bauer",
                    "start_date": "1912",
                    "end_date": "1938",
                    "source_url": EXPECTED_ENTITY_URL,
                },
                {
                    "owner": "Austrian State Gallery",
                    "start_date": "1945",
                    "end_date": "2006",
                    "source_url": EXPECTED_ENTITY_URL,
                },
            ],
            collections=[
                {
                    "collection_name": "Neue Galerie New York",
                    "source_url": EXPECTED_ENTITY_URL,
                },
            ],
            significant_events=[
                {
                    "event_label": "restitution",
                    "date": "2006-01-17",
                    "source_url": EXPECTED_ENTITY_URL,
                },
            ],
        )

        search_keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Gustav Klimt",
            probable_creation_window="1907",
            style_and_movement="Vienna Secession",
            detected_signatures_or_marks=[],
            search_keywords=["klimt", "portrait"],
        )
        facts: list = []
        sources_queried: list = []
        sources_failed: list = []

        await _retrieve_wikidata(search_keys, facts, sources_queried, sources_failed)

        # Should have produced 4 facts (2 ownership + 1 collection + 1 event)
        assert len(facts) == 4, f"Expected 4 facts, got {len(facts)}"

        # ALL facts must have byte-identical source_url equal to the entity URI
        for i, fact in enumerate(facts):
            assert fact.source_url == EXPECTED_ENTITY_URL, (
                f"Fact {i} source_url mismatch: "
                f"expected {EXPECTED_ENTITY_URL!r}, "
                f"got {fact.source_url!r}"
            )
            # Also verify source_entity_id matches
            assert fact.source_entity_id == EXPECTED_ENTITY_URL, (
                f"Fact {i} source_entity_id mismatch: "
                f"expected {EXPECTED_ENTITY_URL!r}, "
                f"got {fact.source_entity_id!r}"
            )


class TestRejectedFactCount:
    """Test that malformed URLs are rejected and counted."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    @patch("artgents.clients.wikidata.WikidataClient.query_provenance", new_callable=AsyncMock)
    async def test_malformed_url_rejected_and_counted(self, mock_query):
        """Facts with malformed source_url are rejected; rejected_fact_count
        reflects the count and retrieved_facts only contains valid entries."""
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.provenance_legal import _retrieve_wikidata
        from artgents.clients.wikidata import WikidataProvenance

        GOOD_URL = "http://www.wikidata.org/entity/Q12345"
        BAD_URL = "http://www.wikidata.2org/entity/Q12345"  # garbled TLD

        mock_query.return_value = WikidataProvenance(
            entity_url=BAD_URL,  # entity itself has a bad URL
            ownership_history=[
                {"owner": "Owner A", "start_date": "1900", "end_date": "1920", "source_url": BAD_URL},
                {"owner": "Owner B", "start_date": "1920", "end_date": "1950", "source_url": GOOD_URL},
            ],
            collections=[
                {"collection_name": "Good Museum", "source_url": GOOD_URL},
            ],
            significant_events=[],
        )

        search_keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Test Artist",
            probable_creation_window="1900",
            style_and_movement="Test",
            detected_signatures_or_marks=[],
            search_keywords=["test"],
        )
        facts: list = []
        sources_queried: list = []
        sources_failed: list = []
        rejected_counts: list = [0]

        await _retrieve_wikidata(
            search_keys, facts, sources_queried, sources_failed, rejected_counts
        )

        # Only facts with valid URLs should be in the list
        assert len(facts) == 2, f"Expected 2 valid facts, got {len(facts)}: {facts}"
        for fact in facts:
            assert "2org" not in fact.source_url, f"Malformed URL leaked through: {fact.source_url}"
            assert fact.source_url == GOOD_URL

        # The malformed one should be counted as rejected
        assert rejected_counts[0] == 1, f"Expected 1 rejection, got {rejected_counts[0]}"

    def test_is_valid_url_catches_garbled_tld(self):
        """_is_valid_url rejects URLs with digits in TLD."""
        from artgents.agents.provenance_legal import _is_valid_url

        assert _is_valid_url("http://www.wikidata.org/entity/Q123") is True
        assert _is_valid_url("https://www.metmuseum.org/art/123") is True
        assert _is_valid_url("http://www.wikidata.2org/entity/Q123") is False
        assert _is_valid_url("http://example.c0m/page") is False
        assert _is_valid_url("") is False
        assert _is_valid_url("not-a-url") is False


class TestWikidataClientLimitInjection:
    """Test that WikidataClient injects a default LIMIT when absent."""

    def test_query_without_limit_gets_default_appended(self):
        """A query with no LIMIT clause gets the default appended."""
        client = WikidataClient(default_limit=50)
        query = "SELECT ?item WHERE { ?item wdt:P31 wd:Q5 . }"
        result = client._ensure_limit(query)
        assert "LIMIT 50" in result
        assert result.endswith("LIMIT 50\n")

    def test_query_with_existing_limit_not_modified(self):
        """A query that already has LIMIT is sent unmodified."""
        client = WikidataClient(default_limit=50)
        query = "SELECT ?item WHERE { ?item wdt:P31 wd:Q5 . } LIMIT 10"
        result = client._ensure_limit(query)
        assert result == query  # unchanged
        assert "LIMIT 50" not in result
        assert "LIMIT 10" in result

    def test_query_with_lowercase_limit_not_modified(self):
        """Case-insensitive detection of existing LIMIT."""
        client = WikidataClient(default_limit=50)
        query = "SELECT ?item WHERE { ?item wdt:P31 wd:Q5 . } limit 25"
        result = client._ensure_limit(query)
        assert result == query
        assert "LIMIT 50" not in result

    def test_default_limit_overridable_via_constructor(self):
        """The default limit can be set to a custom value."""
        client = WikidataClient(default_limit=20)
        query = "SELECT ?item WHERE { ?item wdt:P31 wd:Q5 . }"
        result = client._ensure_limit(query)
        assert "LIMIT 20" in result
        assert "LIMIT 50" not in result

    def test_default_limit_zero_disables_injection(self):
        """Setting default_limit=0 disables LIMIT injection entirely."""
        client = WikidataClient(default_limit=0)
        query = "SELECT ?item WHERE { ?item wdt:P31 wd:Q5 . }"
        result = client._ensure_limit(query)
        assert result == query
        assert "LIMIT" not in result

    def test_provenance_query_no_longer_has_hardcoded_limit(self):
        """_build_provenance_query no longer hardcodes LIMIT — it's the client's job."""
        client = WikidataClient(default_limit=50)
        query = client._build_provenance_query("Claude Monet", "1880")
        # The raw query should NOT have LIMIT (client adds it in _execute_sparql)
        import re
        assert not re.search(r"\bLIMIT\b", query, re.IGNORECASE), (
            "Query should not have hardcoded LIMIT — the client injects it"
        )

    @patch("httpx.AsyncClient.request", new_callable=AsyncMock)
    async def test_execute_sparql_receives_limited_query(self, mock_request):
        """The actual SPARQL sent to the endpoint includes the injected LIMIT."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": {"bindings": []}}
        mock_request.return_value = mock_response

        async with WikidataClient(default_limit=50) as client:
            await client.query_provenance(artist="Claude Monet")

        # Check what query was actually sent via HTTP POST
        call_kwargs = mock_request.call_args
        sent_data = call_kwargs.kwargs.get("data") or call_kwargs[1].get("data", {})
        sent_query = sent_data.get("query", "")
        sent_query = sent_data.get("query", "")
        assert "LIMIT 50" in sent_query, f"Expected LIMIT 50 in query, got: {sent_query[-100:]}"

    def test_reduced_timeout(self):
        """Default timeout is 15s, not 30s."""
        client = WikidataClient()
        assert client._client.timeout.connect == 15.0 or client._client.timeout.read == 15.0
