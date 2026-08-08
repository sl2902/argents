"""Unit tests for pipeline orchestration.

Tests correct call ordering, concurrency of stages 2 and 3, result aggregation,
and error propagation — all with mocked agent functions.
"""

from __future__ import annotations

import asyncio
import base64
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from artgents.pipeline import PipelineInput, PipelineResult, run_pipeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_input() -> PipelineInput:
    """Minimal valid pipeline input."""
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    return PipelineInput(
        images=[base64.b64encode(jpeg_bytes).decode()],
        known_artist="Claude Monet",
    )


@pytest.fixture
def mock_visual_output():
    """Mocked VisualAnalysisOutput."""
    output = MagicMock()
    output.is_artwork = True
    output.is_artwork_reasoning = "Image shows a painting"
    output.search_keys.primary_artist_attribution = "Attributed to Claude Monet"
    output.search_keys.work_title = None
    output.search_keys.probable_creation_window = "1900–1910"
    output.search_keys.style_and_movement = "Impressionism"
    return output


@pytest.fixture
def mock_title_risk():
    """Mocked TitleRiskMatrix."""
    risk = MagicMock()
    risk.requires_human_review = False
    risk.synthesis_summary = "Both agree: low risk"
    return risk


@pytest.fixture
def mock_valuation_output():
    """Mocked FinancialValuationResult."""
    val = MagicMock()
    val.requires_human_review = False
    val.valuation_corridor.low_estimate_usd = 1_000_000
    val.valuation_corridor.high_estimate_usd = 3_000_000
    return val


@pytest.fixture
def mock_curator_ah():
    """Mocked CuratorOutput for auction_house."""
    output = MagicMock()
    output.variant_used = "auction_house"
    output.exhibition_narrative = "Auction narrative"
    output.wall_label = "Monet, c. 1905"
    output.suggested_title = "Untitled Landscape"
    output.disclosures = []
    return output


@pytest.fixture
def mock_curator_pg():
    """Mocked CuratorOutput for public_gallery."""
    output = MagicMock()
    output.variant_used = "public_gallery"
    output.exhibition_narrative = "Gallery narrative"
    output.wall_label = "Attributed to Monet"
    output.suggested_title = "Untitled Landscape"
    output.disclosures = []
    return output


# ---------------------------------------------------------------------------
# TestPipelineModels
# ---------------------------------------------------------------------------


class TestPipelineModels:
    """Test PipelineInput and PipelineResult models."""

    def test_pipeline_input_minimal(self):
        jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 100).decode()
        inp = PipelineInput(images=[jpeg])
        assert inp.known_title is None
        assert "variant_key" not in PipelineInput.model_fields

    def test_pipeline_input_full(self):
        jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 100).decode()
        inp = PipelineInput(
            images=[jpeg],
            known_title="Water Lilies",
            known_artist="Monet",
            known_period="1906",
            medium="oil on canvas",
        )
        assert inp.known_title == "Water Lilies"

    def test_pipeline_input_empty_images_rejected(self):
        with pytest.raises(Exception):
            PipelineInput(images=[])

    def test_pipeline_result_exposes_both_curator_variants(self):
        result = PipelineResult.model_construct(
            visual_analysis=MagicMock(),
            title_risk=MagicMock(),
            valuation=MagicMock(),
            curator_output_auction_house=MagicMock(),
            curator_output_public_gallery=MagicMock(),
        )
        assert result.curator_output_auction_house is not None
        assert result.curator_output_public_gallery is not None


# ---------------------------------------------------------------------------
# TestPipelineOrchestration
# ---------------------------------------------------------------------------


class TestPipelineOrchestration:
    """Test correct call ordering and result aggregation."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_correct_call_order(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
        mock_title_risk,
        mock_valuation_output,
        mock_curator_ah,
        mock_curator_pg,
    ):
        """Agents are called in correct order with correct inputs."""
        mock_analyze.return_value = mock_visual_output
        mock_provenance.return_value = mock_title_risk
        mock_valuation.return_value = mock_valuation_output
        # curate is called twice (both variants)
        mock_curate.side_effect = [mock_curator_ah, mock_curator_pg]

        result = await run_pipeline(sample_input)

        # Stage 1 called
        mock_analyze.assert_called_once()
        # Stage 2 both called with search_keys
        mock_provenance.assert_called_once()
        mock_valuation.assert_called_once()
        # Verify search_keys was the first positional arg
        assert mock_provenance.call_args[0][0] == mock_visual_output.search_keys
        assert mock_valuation.call_args[0][0] == mock_visual_output.search_keys
        # Stage 3: curate called TWICE (both variants)
        assert mock_curate.call_count == 2

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_result_contains_both_variants(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
        mock_title_risk,
        mock_valuation_output,
        mock_curator_ah,
        mock_curator_pg,
    ):
        """PipelineResult exposes both Curator variants."""
        mock_analyze.return_value = mock_visual_output
        mock_provenance.return_value = mock_title_risk
        mock_valuation.return_value = mock_valuation_output
        mock_curate.side_effect = [mock_curator_ah, mock_curator_pg]

        result = await run_pipeline(sample_input)

        assert result.visual_analysis is mock_visual_output
        assert result.title_risk is mock_title_risk
        assert result.valuation is mock_valuation_output
        assert result.curator_output_auction_house is mock_curator_ah
        assert result.curator_output_public_gallery is mock_curator_pg


# ---------------------------------------------------------------------------
# TestConcurrency
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Verify stages 2 and 3 run their sub-tasks concurrently."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_stage2_runs_concurrently(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
    ):
        """Stage 2 agents run concurrently — total time ≈ max(both), not sum."""
        delay = 0.3

        async def slow_provenance(*args, **kwargs):
            await asyncio.sleep(delay)
            result = MagicMock()
            result.requires_human_review = False
            return result

        async def slow_valuation(*args, **kwargs):
            await asyncio.sleep(delay)
            result = MagicMock()
            result.requires_human_review = False
            return result

        mock_analyze.return_value = mock_visual_output
        mock_provenance.side_effect = slow_provenance
        mock_valuation.side_effect = slow_valuation
        mock_curate.return_value = MagicMock()

        start = time.perf_counter()
        await run_pipeline(sample_input)
        elapsed = time.perf_counter() - start

        assert elapsed < delay * 1.8, (
            f"Stage 2 appears sequential: elapsed {elapsed:.2f}s"
        )

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_stage3_curator_variants_run_concurrently(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
    ):
        """Both Curator variants run concurrently in stage 3."""
        delay = 0.3

        async def slow_curate(*args, **kwargs):
            await asyncio.sleep(delay)
            return MagicMock()

        mock_analyze.return_value = mock_visual_output
        mock_provenance.return_value = MagicMock(requires_human_review=False)
        mock_valuation.return_value = MagicMock(requires_human_review=False)
        mock_curate.side_effect = slow_curate

        start = time.perf_counter()
        await run_pipeline(sample_input)
        elapsed = time.perf_counter() - start

        # Two curate calls at 300ms each — if sequential would be 600ms+
        assert elapsed < delay * 1.8, (
            f"Stage 3 curator variants appear sequential: elapsed {elapsed:.2f}s"
        )
        assert mock_curate.call_count == 2


# ---------------------------------------------------------------------------
# TestErrorPropagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """Test that errors from any stage propagate without suppression."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_stage1_error_propagates(self, mock_analyze, sample_input):
        """Visual Art Historian failure propagates directly."""
        from artgents.agents.art_historian import InvalidImageError

        mock_analyze.side_effect = InvalidImageError("Bad image")

        with pytest.raises(InvalidImageError, match="Bad image"):
            await run_pipeline(sample_input)

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_stage2_error_propagates(
        self, mock_analyze, mock_provenance, mock_valuation, mock_curate,
        sample_input, mock_visual_output,
    ):
        """Stage 2 failure propagates."""
        from artgents.clients.vertex import VertexCallError

        mock_analyze.return_value = mock_visual_output
        mock_provenance.side_effect = VertexCallError("Vertex down")
        mock_valuation.return_value = MagicMock(requires_human_review=False)

        with pytest.raises(VertexCallError, match="Vertex down"):
            await run_pipeline(sample_input)

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_stage3_curator_error_propagates(
        self, mock_analyze, mock_provenance, mock_valuation, mock_curate,
        sample_input, mock_visual_output,
    ):
        """Curator failure propagates."""
        from artgents.clients.vertex import VertexCallError

        mock_analyze.return_value = mock_visual_output
        mock_provenance.return_value = MagicMock(requires_human_review=False)
        mock_valuation.return_value = MagicMock(requires_human_review=False)
        mock_curate.side_effect = VertexCallError("Curator error")

        with pytest.raises(VertexCallError, match="Curator error"):
            await run_pipeline(sample_input)


# ---------------------------------------------------------------------------
# TestNotArtworkGate
# ---------------------------------------------------------------------------


class TestNotArtworkGate:
    """Test that is_artwork=False stops the pipeline immediately."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_not_artwork_raises_and_skips_downstream(
        self, mock_analyze, mock_provenance, mock_valuation, mock_curate,
        sample_input,
    ):
        """If is_artwork=False, NotArtworkError raised and no downstream agents called."""
        from artgents.pipeline import NotArtworkError

        not_artwork_output = MagicMock()
        not_artwork_output.is_artwork = False
        not_artwork_output.is_artwork_reasoning = "Image shows a person, not an artwork"
        not_artwork_output.search_keys.primary_artist_attribution = "Unknown"

        mock_analyze.return_value = not_artwork_output

        with pytest.raises(NotArtworkError, match="person, not an artwork"):
            await run_pipeline(sample_input)

        mock_provenance.assert_not_called()
        mock_valuation.assert_not_called()
        mock_curate.assert_not_called()
