"""Unit tests for pipeline orchestration.

Tests correct call ordering, concurrency of stage 2, result aggregation,
and error propagation — all with mocked agent functions.
"""

from __future__ import annotations

import asyncio
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
    import base64

    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    return PipelineInput(
        images=[base64.b64encode(jpeg_bytes).decode()],
        known_artist="Claude Monet",
        variant_key="public_gallery",
    )


@pytest.fixture
def mock_visual_output():
    """Mocked VisualAnalysisOutput."""
    output = MagicMock()
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
def mock_curator_output():
    """Mocked CuratorOutput."""
    output = MagicMock()
    output.variant_used = "public_gallery"
    output.exhibition_narrative = "A narrative..."
    output.wall_label = "Monet, c. 1905"
    output.suggested_title = "Untitled Landscape"
    output.disclosures = []
    return output


# ---------------------------------------------------------------------------
# TestPipelineModels
# ---------------------------------------------------------------------------


class TestPipelineModels:
    """Test PipelineInput and PipelineResult models."""

    def test_pipeline_input_minimal(self):
        import base64

        jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 100).decode()
        inp = PipelineInput(images=[jpeg])
        assert inp.known_title is None
        assert inp.variant_key is None

    def test_pipeline_input_full(self):
        import base64

        jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 100).decode()
        inp = PipelineInput(
            images=[jpeg],
            known_title="Water Lilies",
            known_artist="Monet",
            known_period="1906",
            medium="oil on canvas",
            variant_key="auction_house",
        )
        assert inp.known_title == "Water Lilies"
        assert inp.variant_key == "auction_house"

    def test_pipeline_input_empty_images_rejected(self):
        with pytest.raises(Exception):
            PipelineInput(images=[])

    def test_pipeline_result_exposes_all_outputs(self):
        result = PipelineResult.model_construct(
            visual_analysis=MagicMock(),
            title_risk=MagicMock(),
            valuation=MagicMock(),
            curator_output=MagicMock(),
        )
        assert result.visual_analysis is not None
        assert result.title_risk is not None
        assert result.valuation is not None
        assert result.curator_output is not None


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
        mock_curator_output,
    ):
        """Agents are called in correct order with correct inputs."""
        mock_analyze.return_value = mock_visual_output
        mock_provenance.return_value = mock_title_risk
        mock_valuation.return_value = mock_valuation_output
        mock_curate.return_value = mock_curator_output

        result = await run_pipeline(sample_input)

        # Stage 1 called
        mock_analyze.assert_called_once()
        # Stage 2 both called with search_keys
        mock_provenance.assert_called_once_with(mock_visual_output.search_keys)
        mock_valuation.assert_called_once_with(mock_visual_output.search_keys)
        # Stage 3 called with all prior outputs
        mock_curate.assert_called_once()
        curator_arg = mock_curate.call_args[0][0]
        assert curator_arg.visual_analysis == mock_visual_output
        assert curator_arg.title_risk == mock_title_risk
        assert curator_arg.valuation == mock_valuation_output
        assert curator_arg.variant_key == "public_gallery"

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_result_contains_all_outputs(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
        mock_title_risk,
        mock_valuation_output,
        mock_curator_output,
    ):
        """PipelineResult exposes all intermediate + final outputs."""
        mock_analyze.return_value = mock_visual_output
        mock_provenance.return_value = mock_title_risk
        mock_valuation.return_value = mock_valuation_output
        mock_curate.return_value = mock_curator_output

        result = await run_pipeline(sample_input)

        assert result.visual_analysis is mock_visual_output
        assert result.title_risk is mock_title_risk
        assert result.valuation is mock_valuation_output
        assert result.curator_output is mock_curator_output


# ---------------------------------------------------------------------------
# TestConcurrency — stage 2 must run in parallel
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Verify stage 2 agents run concurrently, not sequentially."""

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
        mock_curator_output,
    ):
        """Stage 2 agents run concurrently — total time ≈ max(both), not sum."""
        delay = 0.3  # 300ms per mock agent

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
        mock_curate.return_value = mock_curator_output

        start = time.perf_counter()
        await run_pipeline(sample_input)
        elapsed = time.perf_counter() - start

        # If sequential: ~600ms. If concurrent: ~300ms.
        # Allow generous margin but assert it's not sequential.
        assert elapsed < delay * 1.8, (
            f"Stage 2 appears sequential: elapsed {elapsed:.2f}s "
            f"(expected < {delay * 1.8:.2f}s for concurrent execution)"
        )

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_both_stage2_agents_called_simultaneously(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
        mock_curator_output,
    ):
        """Both stage 2 agents are in-flight at the same time."""
        in_flight = []

        async def track_provenance(*args, **kwargs):
            in_flight.append("provenance_start")
            await asyncio.sleep(0.1)
            in_flight.append("provenance_end")
            result = MagicMock()
            result.requires_human_review = False
            return result

        async def track_valuation(*args, **kwargs):
            in_flight.append("valuation_start")
            await asyncio.sleep(0.1)
            in_flight.append("valuation_end")
            result = MagicMock()
            result.requires_human_review = False
            return result

        mock_analyze.return_value = mock_visual_output
        mock_provenance.side_effect = track_provenance
        mock_valuation.side_effect = track_valuation
        mock_curate.return_value = mock_curator_output

        await run_pipeline(sample_input)

        # Both should start before either ends (concurrent)
        starts = [i for i, x in enumerate(in_flight) if "start" in x]
        ends = [i for i, x in enumerate(in_flight) if "end" in x]
        assert len(starts) == 2
        assert all(s < min(ends) for s in starts), (
            f"Both agents should start before either ends. Order: {in_flight}"
        )


# ---------------------------------------------------------------------------
# TestErrorPropagation — no suppression
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
    async def test_stage2_provenance_error_propagates(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
    ):
        """Provenance/Legal failure propagates — no partial recovery."""
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
    async def test_stage2_valuation_error_propagates(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
    ):
        """Financial Valuation failure propagates — no partial recovery."""
        from artgents.clients.vertex import VertexCallError

        mock_analyze.return_value = mock_visual_output
        mock_provenance.return_value = MagicMock(requires_human_review=False)
        mock_valuation.side_effect = VertexCallError("Vertex timeout")

        with pytest.raises(VertexCallError, match="Vertex timeout"):
            await run_pipeline(sample_input)

    @patch("artgents.pipeline.curate", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_valuation", new_callable=AsyncMock)
    @patch("artgents.pipeline.assess_provenance", new_callable=AsyncMock)
    @patch("artgents.pipeline.analyze_artwork", new_callable=AsyncMock)
    async def test_stage3_curator_error_propagates(
        self,
        mock_analyze,
        mock_provenance,
        mock_valuation,
        mock_curate,
        sample_input,
        mock_visual_output,
    ):
        """Curator failure propagates."""
        from artgents.clients.vertex import VertexCallError

        mock_analyze.return_value = mock_visual_output
        mock_provenance.return_value = MagicMock(requires_human_review=False)
        mock_valuation.return_value = MagicMock(requires_human_review=False)
        mock_curate.side_effect = VertexCallError("Curator model error")

        with pytest.raises(VertexCallError, match="Curator model error"):
            await run_pipeline(sample_input)
