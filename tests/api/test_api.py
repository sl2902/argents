"""Unit tests for the Artgents API layer.

Tests endpoints, response model transformations, and error handling
with a fully mocked pipeline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from artgents.agents.art_historian import InvalidImageError
from artgents.agents.financial_valuation import (
    BullishSpecialistOutput,
    ConservativeAppraiserOutput,
    ValuationCorridor,
)
from artgents.agents.provenance_legal import (
    ComplianceAuditorOutput,
    ProvenanceHistorianOutput,
)
from artgents.api.app import app
from artgents.api.response_models import (
    MAX_DESCRIPTION_LENGTH,
    MAX_EVIDENCE_SAMPLE,
    build_analyze_response,
)
from artgents.clients.parallel import CreditExhaustedError
from artgents.clients.vertex import VertexCallError
from artgents.pipeline import PipelineResult, StageTiming

client = TestClient(app)

# Fake JPEG content for uploads
JPEG_CONTENT = b"\xff\xd8\xff\xe0" + b"\x00" * 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compliance_auditor() -> ComplianceAuditorOutput:
    return ComplianceAuditorOutput.model_construct(
        identified_gaps=[],
        risk_level="low",
        reasoning="No significant gaps identified.",
    )


def _make_provenance_historian() -> ProvenanceHistorianOutput:
    return ProvenanceHistorianOutput.model_construct(
        contextual_notes="Clean provenance through known collections.",
        cited_evidence=[],
        risk_level="low",
    )


def _make_conservative_appraiser() -> ConservativeAppraiserOutput:
    return ConservativeAppraiserOutput.model_construct(
        floor_estimate_usd=200000.0,
        methodology="Anchored on 2022 Impressionist sales at Christie's",
        primary_comp="Monet, Water Lilies, sold for $180k in 2022",
        confidence="moderate",
    )


def _make_bullish_specialist() -> BullishSpecialistOutput:
    return BullishSpecialistOutput.model_construct(
        ceiling_estimate_usd=400000.0,
        methodology="Based on premium Argenteuil-period Monet demand",
        primary_comp="Monet, Bridge at Argenteuil, sold for $450k in 2023",
        confidence="moderate",
    )


def _make_valuation_corridor() -> ValuationCorridor:
    return ValuationCorridor.model_construct(
        low_estimate_usd=200000.0,
        high_estimate_usd=400000.0,
    )


def _build_mock_pipeline_result() -> PipelineResult:
    """Construct a PipelineResult with MagicMock sub-objects for testing."""

    # Visual analysis mock
    mock_visual = MagicMock()
    mock_visual.search_keys.primary_artist_attribution = "Claude Monet"
    mock_visual.search_keys.probable_creation_window = "1870-1880"
    mock_visual.search_keys.style_and_movement = "Impressionism"
    mock_visual.composition_analysis = "Loose brushwork with water reflections"
    mock_visual.condition_notes = "Minor craquelure in upper left"
    mock_visual.stylistic_authenticity_notes = "Consistent with Monet's Argenteuil period"

    # Title risk (provenance) mock
    mock_risk = MagicMock()
    mock_risk.compliance_auditor = _make_compliance_auditor()
    mock_risk.provenance_historian = _make_provenance_historian()
    mock_risk.evidence_bundle.retrieved_facts = [
        MagicMock(
            claim=f"Provenance fact {i}",
            source_url=f"https://example.com/prov/{i}",
            source_type="wikidata",
        )
        for i in range(12)
    ]
    mock_risk.requires_human_review = False
    mock_risk.synthesis_summary = "Both sub-agents agree: low risk."

    # Valuation mock
    mock_val = MagicMock()
    mock_val.conservative_appraiser = _make_conservative_appraiser()
    mock_val.bullish_specialist = _make_bullish_specialist()
    mock_val.valuation_corridor = _make_valuation_corridor()
    mock_val.corridor_summary = "Estimated $200k-$400k corridor"
    mock_val.requires_human_review = False
    mock_val.evidence.comparable_sales = [
        MagicMock(
            description=f"Comparable sale {i}",
            source_url=f"https://example.com/sale/{i}",
            source_type="parallel_search",
        )
        for i in range(10)
    ]

    # Curator mock
    mock_curator = MagicMock()
    mock_curator.exhibition_narrative = "A stunning work from the Impressionist era."
    mock_curator.wall_label = "Monet, Water Lilies, c. 1875"
    mock_curator.suggested_title = "Reflections at Argenteuil"
    mock_curator.disclosures = ["AI-generated analysis"]
    mock_curator.variant_used = "scholarly"

    timings = StageTiming(
        visual_analysis_ms=100,
        provenance_ms=200,
        valuation_ms=180,
        stage_2_wall_clock_ms=210,
        curator_ms=150,
        total_ms=460,
    )

    return PipelineResult.model_construct(
        visual_analysis=mock_visual,
        title_risk=mock_risk,
        valuation=mock_val,
        curator_output=mock_curator,
        timings=timings,
    )


# ---------------------------------------------------------------------------
# TestHealthEndpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_200_ok(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_requires_no_external_calls(self):
        """Health endpoint should return instantly with no mocking needed."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# TestAnalyzeEndpoint
# ---------------------------------------------------------------------------


class TestAnalyzeEndpoint:
    """Tests for POST /api/analyze with mocked pipeline."""

    @patch("artgents.api.routes.run_pipeline", new_callable=AsyncMock)
    def test_success_returns_200_with_expected_shape(self, mock_run_pipeline):
        mock_result = _build_mock_pipeline_result()
        mock_run_pipeline.return_value = mock_result

        response = client.post(
            "/api/analyze",
            files=[("files", ("test.jpg", JPEG_CONTENT, "image/jpeg"))],
        )

        assert response.status_code == 200
        data = response.json()

        # Verify top-level keys
        assert "attribution" in data
        assert "period_style" in data
        assert "composition_analysis" in data
        assert "condition_notes" in data
        assert "stylistic_authenticity_notes" in data
        assert "provenance_synthesis_summary" in data
        assert "corridor_summary" in data
        assert "exhibition_narrative" in data
        assert "wall_label" in data
        assert "suggested_title" in data
        assert "disclosures" in data
        assert "variant_used" in data
        assert "provenance_evidence_sample" in data
        assert "valuation_evidence_sample" in data
        assert "total_provenance_facts" in data
        assert "total_valuation_comps" in data
        assert "timings" in data

        # Verify timings shape
        timings = data["timings"]
        assert timings["visual_analysis_ms"] == 100
        assert timings["total_ms"] == 460

    @patch("artgents.api.routes.run_pipeline", new_callable=AsyncMock)
    def test_invalid_image_error_returns_400(self, mock_run_pipeline):
        mock_run_pipeline.side_effect = InvalidImageError("Cannot decode image")

        response = client.post(
            "/api/analyze",
            files=[("files", ("bad.jpg", JPEG_CONTENT, "image/jpeg"))],
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Cannot decode image"
        assert data["stage"] == "visual_art_historian"

    @patch("artgents.api.routes.run_pipeline", new_callable=AsyncMock)
    def test_vertex_call_error_returns_502(self, mock_run_pipeline):
        mock_run_pipeline.side_effect = VertexCallError("Model unavailable")

        response = client.post(
            "/api/analyze",
            files=[("files", ("test.jpg", JPEG_CONTENT, "image/jpeg"))],
        )

        assert response.status_code == 502
        data = response.json()
        assert data["error"] == "Model unavailable"
        assert data["stage"] == "model_call"

    @patch("artgents.api.routes.run_pipeline", new_callable=AsyncMock)
    def test_credit_exhausted_error_returns_503(self, mock_run_pipeline):
        mock_run_pipeline.side_effect = CreditExhaustedError("No credits remaining")

        response = client.post(
            "/api/analyze",
            files=[("files", ("test.jpg", JPEG_CONTENT, "image/jpeg"))],
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "No credits remaining"
        assert data["stage"] == "retrieval"

    def test_no_files_uploaded_returns_422(self):
        """FastAPI validation rejects request with no files field."""
        response = client.post("/api/analyze")
        assert response.status_code == 422

    @patch("artgents.api.routes.run_pipeline", new_callable=AsyncMock)
    def test_multiple_files_accepted(self, mock_run_pipeline):
        mock_result = _build_mock_pipeline_result()
        mock_run_pipeline.return_value = mock_result

        response = client.post(
            "/api/analyze",
            files=[
                ("files", ("img1.jpg", JPEG_CONTENT, "image/jpeg")),
                ("files", ("img2.jpg", JPEG_CONTENT, "image/jpeg")),
            ],
        )

        assert response.status_code == 200
        # Verify pipeline was called with 2 images
        call_args = mock_run_pipeline.call_args[0][0]
        assert len(call_args.images) == 2


# ---------------------------------------------------------------------------
# TestResponseModels
# ---------------------------------------------------------------------------


class TestResponseModels:
    """Tests for build_analyze_response transformation logic."""

    def test_truncates_long_descriptions(self):
        """Descriptions over 300 chars should be truncated with '...'."""
        mock_result = _build_mock_pipeline_result()

        # Set a provenance fact with a very long claim
        long_claim = "A" * 500
        mock_result.title_risk.evidence_bundle.retrieved_facts = [
            MagicMock(
                claim=long_claim,
                source_url="https://example.com/long",
                source_type="wikidata",
            )
        ]
        mock_result.valuation.evidence.comparable_sales = []

        response = build_analyze_response(mock_result)

        sample = response.provenance_evidence_sample[0]
        assert len(sample.description) == MAX_DESCRIPTION_LENGTH
        assert sample.description.endswith("...")

    def test_never_truncates_source_url(self):
        """Source URLs should never be truncated, regardless of length."""
        mock_result = _build_mock_pipeline_result()

        long_url = "https://example.com/" + "x" * 500
        mock_result.title_risk.evidence_bundle.retrieved_facts = [
            MagicMock(
                claim="Short claim",
                source_url=long_url,
                source_type="wikidata",
            )
        ]
        mock_result.valuation.evidence.comparable_sales = []

        response = build_analyze_response(mock_result)

        sample = response.provenance_evidence_sample[0]
        assert sample.source_url == long_url

    def test_evidence_sampling_limits_to_8(self):
        """Only first 8 evidence entries should be included in the sample."""
        mock_result = _build_mock_pipeline_result()

        # Create 12 provenance facts — only 8 should be sampled
        mock_result.title_risk.evidence_bundle.retrieved_facts = [
            MagicMock(
                claim=f"Fact {i}",
                source_url=f"https://example.com/{i}",
                source_type="wikidata",
            )
            for i in range(12)
        ]

        # Create 10 valuation comps — only 8 should be sampled
        mock_result.valuation.evidence.comparable_sales = [
            MagicMock(
                description=f"Sale {i}",
                source_url=f"https://example.com/sale/{i}",
                source_type="parallel_search",
            )
            for i in range(10)
        ]

        response = build_analyze_response(mock_result)

        assert len(response.provenance_evidence_sample) == MAX_EVIDENCE_SAMPLE
        assert len(response.valuation_evidence_sample) == MAX_EVIDENCE_SAMPLE

    def test_total_counts_reflect_full_evidence(self):
        """total_provenance_facts and total_valuation_comps reflect full counts, not sampled."""
        mock_result = _build_mock_pipeline_result()

        # 12 provenance facts, 10 valuation comps
        mock_result.title_risk.evidence_bundle.retrieved_facts = [
            MagicMock(
                claim=f"Fact {i}",
                source_url=f"https://example.com/{i}",
                source_type="wikidata",
            )
            for i in range(12)
        ]
        mock_result.valuation.evidence.comparable_sales = [
            MagicMock(
                description=f"Sale {i}",
                source_url=f"https://example.com/sale/{i}",
                source_type="parallel_search",
            )
            for i in range(10)
        ]

        response = build_analyze_response(mock_result)

        assert response.total_provenance_facts == 12
        assert response.total_valuation_comps == 10

    def test_short_descriptions_not_truncated(self):
        """Descriptions under 300 chars should remain unchanged."""
        mock_result = _build_mock_pipeline_result()

        short_claim = "A short provenance claim."
        mock_result.title_risk.evidence_bundle.retrieved_facts = [
            MagicMock(
                claim=short_claim,
                source_url="https://example.com/short",
                source_type="wikidata",
            )
        ]
        mock_result.valuation.evidence.comparable_sales = []

        response = build_analyze_response(mock_result)

        sample = response.provenance_evidence_sample[0]
        assert sample.description == short_claim


# ---------------------------------------------------------------------------
# TestErrorHandling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests verifying error response structure and status code mapping."""

    @patch("artgents.api.routes.run_pipeline", new_callable=AsyncMock)
    def test_error_responses_have_error_and_stage_fields(self, mock_run_pipeline):
        """All error responses must include 'error' and 'stage' keys."""
        mock_run_pipeline.side_effect = InvalidImageError("bad image")

        response = client.post(
            "/api/analyze",
            files=[("files", ("test.jpg", JPEG_CONTENT, "image/jpeg"))],
        )

        data = response.json()
        assert "error" in data
        assert "stage" in data

    @patch("artgents.api.routes.run_pipeline", new_callable=AsyncMock)
    def test_invalid_image_maps_to_400(self, mock_run_pipeline):
        mock_run_pipeline.side_effect = InvalidImageError("corrupted")

        response = client.post(
            "/api/analyze",
            files=[("files", ("test.jpg", JPEG_CONTENT, "image/jpeg"))],
        )

        assert response.status_code == 400

    @patch("artgents.api.routes.run_pipeline", new_callable=AsyncMock)
    def test_vertex_call_error_maps_to_502(self, mock_run_pipeline):
        mock_run_pipeline.side_effect = VertexCallError("timeout")

        response = client.post(
            "/api/analyze",
            files=[("files", ("test.jpg", JPEG_CONTENT, "image/jpeg"))],
        )

        assert response.status_code == 502
