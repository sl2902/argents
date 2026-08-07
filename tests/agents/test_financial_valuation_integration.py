"""Integration test: Financial Valuation agent against live external services.

This test is NOT part of the default test suite. It:
- Hits real Parallel Search API (requires credits)
- Hits real Wikidata SPARQL endpoint
- Hits real Vertex AI (requires GCP credentials)

Run manually:
    pytest tests/agents/test_financial_valuation_integration.py -m integration -v

Requires:
    - GCP_PROJECT env var set
    - PARALLEL_WEB_API_KEY env var set (or empty to skip Parallel)
    - Valid Application Default Credentials (ADC)
"""

from __future__ import annotations

import pytest

from artgents.agents.art_historian import ProvenanceSearchKeys
from artgents.agents.financial_valuation import (
    FinancialValuationResult,
    assess_valuation,
    gather_comps,
)


@pytest.mark.integration
async def test_gather_comps_real_artist():
    """Gather comparable sales for a well-known artist from live sources."""
    search_keys = ProvenanceSearchKeys(
        primary_artist_attribution="Attributed to Claude Monet",
        probable_creation_window="1900–1910",
        style_and_movement="Impressionism",
        detected_signatures_or_marks=[],
        search_keywords=["monet", "impressionism", "water lilies"],
    )

    evidence = await gather_comps(search_keys)

    print(f"\n--- gather_comps integration result ---")
    print(f"Sources queried: {evidence.sources_queried}")
    print(f"Sources failed: {evidence.sources_failed}")
    print(f"Evidence scope: {evidence.evidence_scope}")
    print(f"Comparable sales: {len(evidence.comparable_sales)}")
    print(f"Rejected: {evidence.rejected_fact_count}")
    for sale in evidence.comparable_sales[:5]:
        price_str = f"${sale.price_usd:,.0f}" if sale.price_usd else "N/A"
        print(f"  [{sale.source_type}] {sale.description[:60]} — {price_str}")
        print(f"    URL: {sale.source_url}")


@pytest.mark.integration
async def test_full_assess_valuation_real():
    """Full valuation assessment against live services."""
    search_keys = ProvenanceSearchKeys(
        work_title="Water Lilies",
        primary_artist_attribution="Attributed to Claude Monet",
        probable_creation_window="1906",
        style_and_movement="Impressionism",
        detected_signatures_or_marks=[],
        search_keywords=["monet", "water lilies", "nympheas"],
    )

    result = await assess_valuation(search_keys)

    assert isinstance(result, FinancialValuationResult)
    assert result.valuation_corridor.low_estimate_usd > 0
    assert result.valuation_corridor.high_estimate_usd >= result.valuation_corridor.low_estimate_usd
    assert result.corridor_summary

    print(f"\n--- Full valuation assessment ---")
    print(f"Corridor: ${result.valuation_corridor.low_estimate_usd:,.0f} – ${result.valuation_corridor.high_estimate_usd:,.0f}")
    print(f"Requires human review: {result.requires_human_review}")
    print(f"Conservative: ${result.conservative_appraiser.floor_estimate_usd:,.0f} ({result.conservative_appraiser.confidence})")
    print(f"Bullish: ${result.bullish_specialist.ceiling_estimate_usd:,.0f} ({result.bullish_specialist.confidence})")
    print(f"Summary: {result.corridor_summary}")
