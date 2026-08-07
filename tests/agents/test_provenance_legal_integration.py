"""Integration test: Provenance & Legal agent against live external services.

This test is NOT part of the default test suite. It:
- Hits real Wikidata SPARQL endpoint
- Hits real Met Museum / AIC APIs
- Hits real Parallel Search API (requires credits)
- Hits real Vertex AI (requires GCP credentials)

Run manually:
    pytest tests/agents/test_provenance_legal_integration.py -m integration -v

Requires:
    - GCP_PROJECT env var set to a valid project with Vertex AI enabled
    - PARALLEL_WEB_API_KEY env var set (or empty to skip Parallel Search)
    - Valid Application Default Credentials (ADC)
    - Network access to Wikidata, Met, AIC, Vertex AI
"""

from __future__ import annotations

import pytest

from artgents.agents.art_historian import ProvenanceSearchKeys
from artgents.agents.provenance_legal import (
    TitleRiskMatrix,
    assess_provenance,
    gather_evidence,
)


@pytest.mark.integration
async def test_gather_evidence_real_wikidata():
    """Gather evidence for a well-known artist from real Wikidata + Met/AIC.

    Uses Van Gogh as a well-documented test case — should get results
    from at least Wikidata and/or Met.
    """
    search_keys = ProvenanceSearchKeys(
        primary_artist_attribution="Attributed to Vincent van Gogh",
        probable_creation_window="1885–1890",
        style_and_movement="Post-Impressionism",
        detected_signatures_or_marks=[],
        search_keywords=["van gogh", "post-impressionism", "oil painting"],
    )

    bundle = await gather_evidence(search_keys)

    # At least some sources should have been queried
    assert len(bundle.sources_queried) > 0, (
        f"Expected at least one source queried, got: "
        f"queried={bundle.sources_queried}, failed={bundle.sources_failed}"
    )

    print(f"\n--- gather_evidence integration result ---")
    print(f"Sources queried: {bundle.sources_queried}")
    print(f"Sources failed: {bundle.sources_failed}")
    print(f"Facts retrieved: {len(bundle.retrieved_facts)}")
    for fact in bundle.retrieved_facts[:10]:
        print(f"  [{fact.source_type}] {fact.claim[:80]}")
        print(f"    URL: {fact.source_url}")


@pytest.mark.integration
async def test_full_assess_provenance_real():
    """Full provenance assessment for a well-documented artist.

    End-to-end: retrieval → dual reasoning (Vertex AI) → synthesis.
    """
    search_keys = ProvenanceSearchKeys(
        primary_artist_attribution="Attributed to Vincent van Gogh",
        probable_creation_window="1885–1890",
        style_and_movement="Post-Impressionism",
        detected_signatures_or_marks=[],
        search_keywords=["van gogh", "post-impressionism", "oil painting"],
    )

    result = await assess_provenance(search_keys)

    assert isinstance(result, TitleRiskMatrix)
    assert result.compliance_auditor.risk_level in ("low", "moderate", "red_flag")
    assert result.provenance_historian.risk_level in ("low", "moderate", "red_flag")
    assert result.synthesis_summary
    assert result.evidence_bundle.sources_queried

    print(f"\n--- Full provenance assessment ---")
    print(f"Compliance Auditor risk_level: {result.compliance_auditor.risk_level}")
    print(f"Provenance Historian risk_level: {result.provenance_historian.risk_level}")
    print(f"Requires human review: {result.requires_human_review}")
    print(f"Synthesis: {result.synthesis_summary}")
    print(f"Auditor reasoning: {result.compliance_auditor.reasoning[:200]}")
    print(f"Historian notes: {result.provenance_historian.contextual_notes[:200]}")
