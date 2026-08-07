"""Integration tests for the Artgents API layer.

These tests hit live services (Vertex AI, Parallel Search) and require
valid GCP credentials. Run with:

    pytest -m integration tests/api/test_api_integration.py
"""

from __future__ import annotations

import pytest
import httpx
from httpx import ASGITransport

from artgents.api.app import app

# Met Museum open-access image (public domain, small size)
MET_IMAGE_URL = (
    "https://images.metmuseum.org/CRDImages/ep/original/DT1567.jpg"
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_analyze_real_image():
    """Full POST /api/analyze with a real image against live services.

    Downloads a painting from the Met's open-access API, sends it to the
    Artgents pipeline, and verifies we get a well-formed response back.

    This test requires:
    - GCP_PROJECT env var set
    - Valid Vertex AI credentials
    - Network access to Met Museum + Parallel Search
    """
    # Download a real artwork image from the Met
    async with httpx.AsyncClient(timeout=30.0) as http:
        img_response = await http.get(MET_IMAGE_URL)
        img_response.raise_for_status()
        image_bytes = img_response.content

    # POST to the Artgents API
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        response = await api_client.post(
            "/api/analyze",
            files=[("files", ("met_painting.jpg", image_bytes, "image/jpeg"))],
            timeout=120.0,
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    # Verify response structure
    assert "attribution" in data
    assert "period_style" in data
    assert "composition_analysis" in data
    assert "condition_notes" in data
    assert "stylistic_authenticity_notes" in data

    # Provenance fields
    assert "compliance_auditor" in data
    assert "provenance_historian" in data
    assert "provenance_synthesis_summary" in data
    assert isinstance(data["provenance_requires_human_review"], bool)

    # Valuation fields
    assert "conservative_appraiser" in data
    assert "bullish_specialist" in data
    assert "valuation_corridor" in data
    assert "corridor_summary" in data
    assert isinstance(data["valuation_requires_human_review"], bool)

    # Curator fields
    assert "exhibition_narrative" in data
    assert len(data["exhibition_narrative"]) > 50
    assert "wall_label" in data
    assert "suggested_title" in data
    assert "disclosures" in data
    assert isinstance(data["disclosures"], list)
    assert "variant_used" in data

    # Evidence sampling
    assert "provenance_evidence_sample" in data
    assert "valuation_evidence_sample" in data
    assert isinstance(data["provenance_evidence_sample"], list)
    assert isinstance(data["valuation_evidence_sample"], list)
    assert len(data["provenance_evidence_sample"]) <= 8
    assert len(data["valuation_evidence_sample"]) <= 8
    assert "total_provenance_facts" in data
    assert "total_valuation_comps" in data

    # Timings
    assert "timings" in data
    timings = data["timings"]
    assert timings["total_ms"] > 0
    assert timings["visual_analysis_ms"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_endpoint_integration():
    """Verify health endpoint works in integration context."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        response = await api_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
