"""Integration test: Curator agent against live Vertex AI.

This test is NOT part of the default test suite. It:
- Hits real Vertex AI (requires GCP credentials)
- Uses realistic fixture data modeled on real upstream agent outputs

Run manually:
    pytest tests/agents/test_curator_integration.py -m integration -v

Requires:
    - GCP_PROJECT env var set
    - Valid Application Default Credentials (ADC)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from artgents.agents.curator import CuratorInput, CuratorOutput, curate


def _make_curator_input(variant_key: str | None = None) -> CuratorInput:
    """Build a realistic CuratorInput from mock upstream outputs."""
    # Visual Analysis
    visual = MagicMock()
    visual.search_keys.primary_artist_attribution = "Attributed to Claude Monet"
    visual.search_keys.work_title = None
    visual.search_keys.probable_creation_window = "1900–1910"
    visual.search_keys.style_and_movement = "Impressionism"
    visual.search_keys.detected_signatures_or_marks = []
    visual.search_keys.search_keywords = ["monet", "water lilies", "impressionism"]
    visual.composition_analysis = (
        "Horizontal composition dominated by a reflective water surface. "
        "Loose, broken brushwork with a vibrant palette of blues, greens, "
        "and purples. Lily pads rendered as gestural color patches."
    )
    visual.condition_notes = (
        "Minor craquelure in upper sky region. No significant losses. "
        "Varnish slightly yellowed."
    )
    visual.stylistic_authenticity_notes = (
        "High confidence in Impressionist attribution (c. 1900–1910). "
        "Moderate-low confidence in specific Monet attribution — no "
        "signature visible, based on stylistic similarity."
    )

    # Title Risk
    title_risk = MagicMock()
    title_risk.requires_human_review = True
    title_risk.synthesis_summary = (
        "Sub-agents DISAGREE on risk level. Compliance Auditor: MODERATE. "
        "Provenance Historian: LOW."
    )
    title_risk.compliance_auditor.risk_level = "moderate"
    title_risk.provenance_historian.risk_level = "low"

    # Financial Valuation
    valuation = MagicMock()
    valuation.requires_human_review = True
    valuation.corridor_summary = (
        "Estimated valuation corridor: $2,000,000 – $15,000,000 USD. "
        "Note: unusually wide spread (7.5x)."
    )
    valuation.valuation_corridor.low_estimate_usd = 2_000_000
    valuation.valuation_corridor.high_estimate_usd = 15_000_000
    valuation.conservative_appraiser.floor_estimate_usd = 2_000_000
    valuation.conservative_appraiser.methodology = "Based on smaller Monet studies."
    valuation.bullish_specialist.ceiling_estimate_usd = 15_000_000
    valuation.bullish_specialist.methodology = "Based on prime Nymphéas sales."

    return CuratorInput.model_construct(
        visual_analysis=visual,
        title_risk=title_risk,
        valuation=valuation,
        variant_key=variant_key,
    )


@pytest.mark.integration
async def test_curate_auction_house_variant():
    """Full Curator run with auction_house variant against live Vertex AI."""
    input_data = _make_curator_input(variant_key="auction_house")
    result = await curate(input_data)

    assert isinstance(result, CuratorOutput)
    assert result.variant_used == "auction_house"
    assert result.exhibition_narrative
    assert result.wall_label
    assert result.suggested_title
    # Disclosures should be present (both flags are True)
    assert len(result.disclosures) >= 2

    print(f"\n--- Curator (auction_house) ---")
    print(f"Variant: {result.variant_used}")
    print(f"Title: {result.suggested_title}")
    print(f"Narrative: {result.exhibition_narrative[:300]}...")
    print(f"Wall label: {result.wall_label}")
    print(f"Disclosures: {result.disclosures}")


@pytest.mark.integration
async def test_curate_public_gallery_variant():
    """Full Curator run with public_gallery variant against live Vertex AI."""
    input_data = _make_curator_input(variant_key="public_gallery")
    result = await curate(input_data)

    assert isinstance(result, CuratorOutput)
    assert result.variant_used == "public_gallery"
    assert result.exhibition_narrative
    assert result.wall_label
    # Public gallery should NOT have dollar figures in narrative/wall_label
    assert "$" not in result.wall_label, (
        f"Public gallery wall_label should not contain dollar figures: {result.wall_label}"
    )

    print(f"\n--- Curator (public_gallery) ---")
    print(f"Variant: {result.variant_used}")
    print(f"Title: {result.suggested_title}")
    print(f"Narrative: {result.exhibition_narrative[:300]}...")
    print(f"Wall label: {result.wall_label}")
    print(f"Disclosures: {result.disclosures}")
