"""Integration test: Full pipeline end-to-end against live services.

This test is NOT part of the default test suite. It:
- Downloads a real image from the Met Museum
- Hits real Vertex AI, Wikidata, Met/AIC APIs, Parallel Search
- Runs all 4 agents sequentially/concurrently as designed

Run manually:
    pytest tests/test_pipeline_integration.py -m integration -v

Requires:
    - GCP_PROJECT env var set
    - PARALLEL_WEB_API_KEY env var set (or empty to skip Parallel)
    - Valid Application Default Credentials (ADC)
    - Network access to all external services
"""

from __future__ import annotations

import base64

import httpx
import pytest

from artgents.pipeline import PipelineInput, PipelineResult, run_pipeline

# Met Museum Open Access — "Wheat Field with Cypresses" by Van Gogh (1889)
MET_IMAGE_URL = (
    "https://images.metmuseum.org/CRDImages/ep/web-large/DP-42549-001.jpg"
)


@pytest.fixture
async def met_image_b64() -> str:
    """Download the Met Open Access test image and return as base64."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(MET_IMAGE_URL)
        response.raise_for_status()
    return base64.b64encode(response.content).decode()


@pytest.mark.integration
async def test_full_pipeline_end_to_end(met_image_b64: str):
    """Full pipeline: image → 4 agents → PipelineResult, no manual intervention.

    This is the acceptance test for the entire project: given a single image,
    produce a complete curated result with all intermediate outputs accessible.
    """
    input_data = PipelineInput(
        images=[met_image_b64],
        known_artist="Vincent van Gogh",
        known_period="1889",
        medium="oil on canvas",
        variant_key="public_gallery",
    )

    result = await run_pipeline(input_data)

    # All four outputs present
    assert result.visual_analysis is not None
    assert result.title_risk is not None
    assert result.valuation is not None
    assert result.curator_output is not None

    # Visual Art Historian produced search_keys
    assert result.visual_analysis.search_keys.primary_artist_attribution
    assert result.visual_analysis.search_keys.style_and_movement

    # Provenance/Legal produced a risk assessment
    assert result.title_risk.requires_human_review in (True, False)
    assert result.title_risk.synthesis_summary

    # Financial Valuation produced a corridor
    assert result.valuation.valuation_corridor.low_estimate_usd > 0
    assert result.valuation.valuation_corridor.high_estimate_usd >= result.valuation.valuation_corridor.low_estimate_usd

    # Curator produced exhibition content
    assert result.curator_output.exhibition_narrative
    assert result.curator_output.wall_label
    assert result.curator_output.variant_used == "public_gallery"

    print(f"\n{'='*60}")
    print(f"FULL PIPELINE RESULT")
    print(f"{'='*60}")
    print(f"\nAttribution: {result.visual_analysis.search_keys.primary_artist_attribution}")
    print(f"Period: {result.visual_analysis.search_keys.probable_creation_window}")
    print(f"Style: {result.visual_analysis.search_keys.style_and_movement}")
    print(f"\nProvenance risk: {result.title_risk.synthesis_summary}")
    print(f"Provenance review: {result.title_risk.requires_human_review}")
    print(f"\nValuation: ${result.valuation.valuation_corridor.low_estimate_usd:,.0f} – ${result.valuation.valuation_corridor.high_estimate_usd:,.0f}")
    print(f"Valuation review: {result.valuation.requires_human_review}")
    print(f"\nVariant: {result.curator_output.variant_used}")
    print(f"Title: {result.curator_output.suggested_title}")
    print(f"Disclosures: {result.curator_output.disclosures}")
    print(f"\nWall label:\n{result.curator_output.wall_label}")
    print(f"\nNarrative:\n{result.curator_output.exhibition_narrative[:500]}...")
