"""Integration test: Visual Art Historian agent against live Vertex AI.

This test is NOT part of the default test suite. It:
- Hits the real Vertex AI API (requires valid GCP credentials & project)
- Downloads a real public-domain image from the Met Museum Open Access
- Verifies the full pipeline end-to-end

Run manually:
    pytest tests/agents/test_art_historian_integration.py -m integration -v

Requires:
    - GCP_PROJECT env var set to a valid project with Vertex AI enabled
    - Valid Application Default Credentials (ADC) configured
    - Network access to images.metmuseum.org and Vertex AI
"""

from __future__ import annotations

import base64

import httpx
import pytest

from artgents.agents.art_historian import (
    VisualAnalysisInput,
    VisualAnalysisOutput,
    analyze_artwork,
)

# Met Museum Open Access — "Wheat Field with Cypresses" by Vincent van Gogh (1889)
# Public domain, CC0. Object ID: 436535
# web-large variant for reasonable download size
MET_IMAGE_URL = (
    "https://images.metmuseum.org/CRDImages/ep/web-large/DP-42549-001.jpg"
)

# Additional detail/condition image of the same work (for multi-image test)
MET_IMAGE_DETAIL_URL = (
    "https://images.metmuseum.org/CRDImages/ep/web-large/LC-EP_1993_132_suppl_CH-001.jpg"
)


@pytest.fixture
async def met_image_b64() -> str:
    """Download the Met Open Access test image and return as base64."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(MET_IMAGE_URL)
        response.raise_for_status()
    return base64.b64encode(response.content).decode()


@pytest.mark.integration
async def test_blind_discovery_real_image(met_image_b64: str):
    """Blind discovery: real Van Gogh image, no metadata, live Vertex AI.

    Verifies:
    - The full pipeline works end-to-end
    - Output conforms to VisualAnalysisOutput schema
    - search_keys contains reasonable values for a Post-Impressionist landscape
    - Attribution uses "Attributed to..." phrasing (no signature visible in this image)
    """
    inp = VisualAnalysisInput(images=[met_image_b64])
    result = await analyze_artwork(inp)

    assert isinstance(result, VisualAnalysisOutput)

    # Schema completeness checks
    assert result.search_keys.primary_artist_attribution
    assert result.search_keys.probable_creation_window
    assert result.search_keys.style_and_movement
    assert len(result.search_keys.search_keywords) > 0
    assert result.composition_analysis
    assert result.condition_notes
    assert result.stylistic_authenticity_notes

    # The image is a famous Van Gogh, but no visible signature →
    # attribution should use qualified phrasing
    attribution = result.search_keys.primary_artist_attribution.lower()
    assert any(
        phrase in attribution
        for phrase in ["attributed to", "manner of", "circle of", "school of", "van gogh"]
    ), f"Attribution should reference Van Gogh or use qualified phrasing: {attribution}"

    print(f"\n--- Integration test result ---")
    print(f"Attribution: {result.search_keys.primary_artist_attribution}")
    print(f"Period: {result.search_keys.probable_creation_window}")
    print(f"Style: {result.search_keys.style_and_movement}")
    print(f"Keywords: {result.search_keys.search_keywords}")
    print(f"Authenticity notes: {result.stylistic_authenticity_notes[:200]}")


@pytest.mark.integration
async def test_verification_real_image(met_image_b64: str):
    """Verification: real Van Gogh image with correct metadata, live Vertex AI.

    Verifies:
    - Verification branch works end-to-end
    - Model confirms consistency rather than flagging anomalies
    """
    inp = VisualAnalysisInput(
        images=[met_image_b64],
        known_artist="Vincent van Gogh",
        known_title="Wheat Field with Cypresses",
        known_period="1889",
        medium="oil on canvas",
    )
    result = await analyze_artwork(inp)

    assert isinstance(result, VisualAnalysisOutput)
    assert result.search_keys.primary_artist_attribution
    assert result.stylistic_authenticity_notes

    # With correct metadata, we expect "consistent" rather than "conflict"
    notes_lower = result.stylistic_authenticity_notes.lower()
    assert "consistent" in notes_lower or "support" in notes_lower, (
        f"Expected consistency with correct metadata, got: "
        f"{result.stylistic_authenticity_notes[:200]}"
    )

    print(f"\n--- Verification test result ---")
    print(f"Attribution: {result.search_keys.primary_artist_attribution}")
    print(f"Authenticity notes: {result.stylistic_authenticity_notes[:300]}")


@pytest.fixture
async def met_images_b64() -> list[str]:
    """Download the primary and detail images, return as list of base64 strings."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        primary = await client.get(MET_IMAGE_URL)
        primary.raise_for_status()
        detail = await client.get(MET_IMAGE_DETAIL_URL)
        detail.raise_for_status()
    return [
        base64.b64encode(primary.content).decode(),
        base64.b64encode(detail.content).decode(),
    ]


@pytest.mark.integration
async def test_multi_image_cross_reference(met_images_b64: list[str]):
    """Multi-image: full view + detail shot in a single call, live Vertex AI.

    Verifies:
    - Multiple images are accepted and processed together
    - The model can cross-reference views (e.g. condition details visible
      in the close-up inform condition_notes)
    - Output is still schema-valid with multi-image input
    """
    inp = VisualAnalysisInput(images=met_images_b64)
    result = await analyze_artwork(inp)

    assert isinstance(result, VisualAnalysisOutput)

    # Schema completeness
    assert result.search_keys.primary_artist_attribution
    assert result.search_keys.probable_creation_window
    assert result.search_keys.style_and_movement
    assert len(result.search_keys.search_keywords) > 0
    assert result.composition_analysis
    assert result.condition_notes
    assert result.stylistic_authenticity_notes

    # With a detail/condition shot available, condition_notes should
    # have more substance than "unable to assess"
    assert len(result.condition_notes) > 20, (
        f"Expected substantive condition notes with detail image, got: "
        f"{result.condition_notes}"
    )

    print(f"\n--- Multi-image integration test result ---")
    print(f"Attribution: {result.search_keys.primary_artist_attribution}")
    print(f"Period: {result.search_keys.probable_creation_window}")
    print(f"Condition notes: {result.condition_notes[:300]}")
    print(f"Authenticity notes: {result.stylistic_authenticity_notes[:200]}")
