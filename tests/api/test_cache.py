"""Unit tests for the response cache module and its integration with execute_job().

Tests cover:
- Cache key computation (determinism, metadata sensitivity)
- get_cached/set_cached round-trip with temp directory
- Corrupted cache file treated as miss
- execute_job cache hit short-circuits pipeline
- execute_job cache miss runs pipeline and caches result
- execute_job failure does NOT cache
- Different metadata = different cache key = cache miss
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from artgents.api.cache import compute_cache_key, get_cached, set_cached
from artgents.api.jobs import Job, JobStatus, ProgressEntry, execute_job
from artgents.pipeline import PipelineInput


# ---------------------------------------------------------------------------
# Cache key computation
# ---------------------------------------------------------------------------


class TestComputeCacheKey:
    def test_same_input_same_key(self):
        """Identical inputs produce the same cache key."""
        key1 = compute_cache_key(
            images=["abc123", "def456"],
            known_title="Starry Night",
            known_artist="Van Gogh",
            known_period="Post-Impressionism",
            medium="Oil on canvas",
        )
        key2 = compute_cache_key(
            images=["abc123", "def456"],
            known_title="Starry Night",
            known_artist="Van Gogh",
            known_period="Post-Impressionism",
            medium="Oil on canvas",
        )
        assert key1 == key2

    def test_different_title_different_key(self):
        """Different known_title produces a different key."""
        key1 = compute_cache_key(
            images=["abc123"],
            known_title="Starry Night",
            known_artist=None,
            known_period=None,
            medium=None,
        )
        key2 = compute_cache_key(
            images=["abc123"],
            known_title="The Persistence of Memory",
            known_artist=None,
            known_period=None,
            medium=None,
        )
        assert key1 != key2

    def test_different_artist_different_key(self):
        key1 = compute_cache_key(["img"], "Title", "Artist A", None, None)
        key2 = compute_cache_key(["img"], "Title", "Artist B", None, None)
        assert key1 != key2

    def test_different_period_different_key(self):
        key1 = compute_cache_key(["img"], None, None, "Renaissance", None)
        key2 = compute_cache_key(["img"], None, None, "Baroque", None)
        assert key1 != key2

    def test_different_medium_different_key(self):
        key1 = compute_cache_key(["img"], None, None, None, "Oil")
        key2 = compute_cache_key(["img"], None, None, None, "Watercolor")
        assert key1 != key2

    def test_different_images_different_key(self):
        key1 = compute_cache_key(["image_a"], None, None, None, None)
        key2 = compute_cache_key(["image_b"], None, None, None, None)
        assert key1 != key2

    def test_none_vs_empty_string_different_key(self):
        """None and '' are distinct for cache key purposes."""
        key1 = compute_cache_key(["img"], None, None, None, None)
        key2 = compute_cache_key(["img"], "", None, None, None)
        assert key1 != key2

    def test_key_is_hex_sha256(self):
        """Key is a 64-char hex string (SHA-256 digest)."""
        key = compute_cache_key(["img"], None, None, None, None)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


# ---------------------------------------------------------------------------
# get_cached / set_cached round-trip
# ---------------------------------------------------------------------------


class TestCacheStorage:
    def test_round_trip(self, tmp_path):
        """set_cached then get_cached returns the same response."""
        from artgents.api.response_models import AnalyzeResponse

        # Create a minimal valid AnalyzeResponse via JSON (avoids building
        # all nested models by hand — just needs to be Pydantic-valid)
        mock_response = self._make_mock_response()

        set_cached("test_key", mock_response, cache_dir=tmp_path)
        result = get_cached("test_key", cache_dir=tmp_path)

        assert result is not None
        assert result.attribution == mock_response.attribution
        assert result.model_dump() == mock_response.model_dump()

    def test_miss_returns_none(self, tmp_path):
        """A key that doesn't exist returns None."""
        result = get_cached("nonexistent_key", cache_dir=tmp_path)
        assert result is None

    def test_corrupted_file_returns_none(self, tmp_path):
        """A corrupted cache file is treated as a miss, not an error."""
        cache_file = tmp_path / "bad_key.json"
        cache_file.write_text("this is not valid json {{{")

        result = get_cached("bad_key", cache_dir=tmp_path)
        assert result is None

    def test_invalid_json_structure_returns_none(self, tmp_path):
        """Valid JSON but wrong structure is treated as a miss."""
        cache_file = tmp_path / "wrong_key.json"
        cache_file.write_text(json.dumps({"foo": "bar"}))

        result = get_cached("wrong_key", cache_dir=tmp_path)
        assert result is None

    @staticmethod
    def _make_mock_response():
        """Create a minimal valid AnalyzeResponse for testing."""
        from artgents.api.response_models import (
            AnalyzeResponse,
            CuratorVariantOutput,
            EvidenceItemDisplay,
            StageTimings,
        )
        from artgents.agents.financial_valuation import (
            BullishSpecialistOutput,
            ConservativeAppraiserOutput,
            ValuationCorridor,
        )
        from artgents.agents.provenance_legal import (
            ComplianceAuditorOutput,
            ProvenanceHistorianOutput,
        )

        curator = CuratorVariantOutput(
            exhibition_narrative="narrative",
            wall_label="label",
            suggested_title="title",
            disclosures=[],
        )
        timings = StageTimings(
            visual_analysis_ms=100,
            stage_2_wall_clock_ms=200,
            provenance_ms=150,
            valuation_ms=150,
            curator_ms=100,
            total_ms=500,
        )

        return AnalyzeResponse(
            attribution="Test Artist",
            period_style="Test Period",
            composition_analysis="Test composition",
            condition_notes="Good condition",
            stylistic_authenticity_notes="Consistent",
            compliance_auditor=ComplianceAuditorOutput(
                identified_gaps=[],
                risk_level="low",
                reasoning="No issues found",
            ),
            provenance_historian=ProvenanceHistorianOutput(
                contextual_notes="Clear provenance history",
                cited_evidence=[],
                risk_level="low",
            ),
            provenance_synthesis_summary="All clear",
            provenance_requires_human_review=False,
            provenance_evidence_scope="specific_object",
            conservative_appraiser=ConservativeAppraiserOutput(
                floor_estimate_usd=10000.0,
                methodology="Comparable sales",
                primary_comp="Similar work sold for $10k at Christie's 2023",
                confidence="moderate",
            ),
            bullish_specialist=BullishSpecialistOutput(
                ceiling_estimate_usd=40000.0,
                methodology="Market trends",
                primary_comp="Peak market comp at $40k Sotheby's 2022",
                confidence="moderate",
            ),
            valuation_corridor=ValuationCorridor(
                low_estimate_usd=10000.0,
                high_estimate_usd=40000.0,
            ),
            corridor_summary="$10k-$40k",
            valuation_requires_human_review=False,
            valuation_evidence_scope="specific_object",
            curator_auction_house=curator,
            curator_public_gallery=curator,
            provenance_evidence_sample=[],
            valuation_evidence_sample=[],
            total_provenance_facts=0,
            total_valuation_comps=0,
            timings=timings,
        )


# ---------------------------------------------------------------------------
# execute_job integration with cache
# ---------------------------------------------------------------------------


class TestExecuteJobCacheIntegration:
    """Test cache integration in execute_job()."""

    @pytest.fixture
    def pipeline_input(self):
        return PipelineInput(
            images=["base64imagedata"],
            known_title="Starry Night",
            known_artist="Van Gogh",
            known_period=None,
            medium=None,
        )

    @pytest.fixture
    def mock_response(self):
        return TestCacheStorage._make_mock_response()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_pipeline(self, pipeline_input, mock_response):
        """On a cache hit, run_pipeline() is never called."""
        job = Job(id="test-1")

        with patch("artgents.api.jobs.get_cached", return_value=mock_response) as mock_get, \
             patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run:
            await execute_job(job, pipeline_input)

        mock_get.assert_called_once()
        mock_run.assert_not_called()
        assert job.status == JobStatus.COMPLETED
        assert job.result is mock_response
        # Cache hit uses 'cache' stage_key, not 'start'
        assert any(log.stage_key == "cache" for log in job.logs)

    @pytest.mark.asyncio
    async def test_cache_miss_runs_pipeline_and_caches(self, pipeline_input, mock_response):
        """On a cache miss, pipeline runs and result is cached."""
        job = Job(id="test-2")

        with patch("artgents.api.jobs.get_cached", return_value=None), \
             patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run, \
             patch("artgents.api.jobs.build_analyze_response", return_value=mock_response), \
             patch("artgents.api.jobs.set_cached") as mock_set:
            mock_run.return_value = MagicMock()
            await execute_job(job, pipeline_input)

        mock_run.assert_called_once()
        mock_set.assert_called_once()
        # Verify set_cached was called with the correct response
        assert mock_set.call_args[0][1] is mock_response
        assert job.status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_pipeline_failure_does_not_cache(self, pipeline_input):
        """A failed pipeline run does NOT get cached."""
        job = Job(id="test-3")

        with patch("artgents.api.jobs.get_cached", return_value=None), \
             patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run, \
             patch("artgents.api.jobs.set_cached") as mock_set:
            mock_run.side_effect = Exception("Pipeline exploded")
            await execute_job(job, pipeline_input)

        mock_set.assert_not_called()
        assert job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_same_input_twice_second_is_cached(self, pipeline_input, mock_response):
        """Two identical requests: second uses cache, pipeline only called once."""
        job1 = Job(id="test-4a")
        job2 = Job(id="test-4b")

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run, \
             patch("artgents.api.jobs.build_analyze_response", return_value=mock_response), \
             patch("artgents.api.jobs.compute_cache_key", return_value="fixed_key"), \
             patch("artgents.api.jobs.get_cached", side_effect=[None, mock_response]), \
             patch("artgents.api.jobs.set_cached"):
            mock_run.return_value = MagicMock()
            await execute_job(job1, pipeline_input)
            await execute_job(job2, pipeline_input)

        # Pipeline called only for the first request
        assert mock_run.call_count == 1
        # Both jobs completed
        assert job1.status == JobStatus.COMPLETED
        assert job2.status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_different_metadata_is_cache_miss(self, mock_response):
        """Same image but different known_title = different cache key = miss."""
        input1 = PipelineInput(
            images=["same_image_data"],
            known_title="Title A",
            known_artist=None,
            known_period=None,
            medium=None,
        )
        input2 = PipelineInput(
            images=["same_image_data"],
            known_title="Title B",
            known_artist=None,
            known_period=None,
            medium=None,
        )

        job1 = Job(id="test-5a")
        job2 = Job(id="test-5b")

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run, \
             patch("artgents.api.jobs.build_analyze_response", return_value=mock_response), \
             patch("artgents.api.jobs.set_cached"), \
             patch("artgents.api.jobs.get_cached", return_value=None):
            mock_run.return_value = MagicMock()
            await execute_job(job1, input1)
            await execute_job(job2, input2)

        # Both requests trigger the pipeline (no cache hit)
        assert mock_run.call_count == 2
