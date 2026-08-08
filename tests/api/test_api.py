"""Unit tests for the Artgents API layer (async job pattern).

Tests the job creation, status polling, and error mapping — all with
mocked pipeline execution.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from artgents.api.app import app
from artgents.api.jobs import JOBS, Job, JobStatus
from artgents.pipeline import StageTiming, PipelineResult

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    """Clear the job store between tests."""
    JOBS.clear()
    yield
    JOBS.clear()


# ---------------------------------------------------------------------------
# TestHealthEndpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200_ok(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_no_agent_calls(self):
        response = client.get("/api/health")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# TestAnalyzeEndpoint — async job creation
# ---------------------------------------------------------------------------


class TestAnalyzeEndpoint:
    def test_analyze_returns_job_id_immediately(self):
        """POST /api/analyze returns a job_id without waiting for completion."""
        jpeg_content = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock()
            response = client.post(
                "/api/analyze",
                files=[("files", ("test.jpg", jpeg_content, "image/jpeg"))],
            )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert isinstance(data["job_id"], str)

    def test_analyze_no_files_returns_400(self):
        """Missing files returns 400."""
        response = client.post("/api/analyze")
        assert response.status_code == 422  # FastAPI validation

    def test_multiple_files_accepted(self):
        """Multiple file uploads are accepted."""
        jpeg_content = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock()
            response = client.post(
                "/api/analyze",
                files=[
                    ("files", ("img1.jpg", jpeg_content, "image/jpeg")),
                    ("files", ("img2.jpg", jpeg_content, "image/jpeg")),
                ],
            )

        assert response.status_code == 200
        assert "job_id" in response.json()


# ---------------------------------------------------------------------------
# TestStatusEndpoint
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    def test_unknown_job_returns_404(self):
        response = client.get("/api/status/nonexistent-id")
        assert response.status_code == 404

    def test_pending_job_shows_status(self):
        """A freshly created job shows pending status."""
        from artgents.api.jobs import create_job

        job = create_job()
        response = client.get(f"/api/status/{job.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["job_id"] == job.id

    def test_running_job_shows_logs(self):
        """A running job shows accumulated structured log messages."""
        from artgents.api.jobs import ProgressEntry, create_job

        job = create_job()
        job.status = JobStatus.RUNNING
        job.logs = [
            ProgressEntry(stage_key="start", message="Starting analysis..."),
            ProgressEntry(stage_key="concurrent_research", message="Researching provenance..."),
        ]

        response = client.get(f"/api/status/{job.id}")
        data = response.json()
        assert data["status"] == "running"
        assert len(data["logs"]) == 2
        assert data["logs"][0]["stage_key"] == "start"
        assert data["logs"][1]["message"] == "Researching provenance..."

    def test_completed_job_includes_result(self):
        """A completed job includes the full result."""
        from artgents.api.jobs import create_job

        job = create_job()
        job.status = JobStatus.COMPLETED
        job.result = MagicMock()
        job.result.model_dump.return_value = {"attribution": "Test", "timings": {}}

        response = client.get(f"/api/status/{job.id}")
        data = response.json()
        assert data["status"] == "completed"
        assert "result" in data
        assert data["result"]["attribution"] == "Test"

    def test_failed_job_includes_error(self):
        """A failed job includes error details."""
        from artgents.api.jobs import create_job

        job = create_job()
        job.status = JobStatus.FAILED
        job.error = "Image is not an artwork"
        job.failed_stage = "visual_art_historian"

        response = client.get(f"/api/status/{job.id}")
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Image is not an artwork"
        assert data["failed_stage"] == "visual_art_historian"


# ---------------------------------------------------------------------------
# TestJobExecution — error mapping
# ---------------------------------------------------------------------------


class TestJobExecution:
    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    @pytest.fixture(autouse=True)
    def _mock_cache(self):
        """Bypass cache layer — these tests use MagicMock pipeline_input
        which isn't JSON-serializable for cache key computation."""
        with patch("artgents.api.jobs.compute_cache_key", return_value="mock_key"), \
             patch("artgents.api.jobs.get_cached", return_value=None), \
             patch("artgents.api.jobs.set_cached"):
            yield

    async def test_invalid_image_maps_to_failed_stage(self):
        from artgents.agents.art_historian import InvalidImageError
        from artgents.api.jobs import create_job, execute_job

        job = create_job()
        pipeline_input = MagicMock()

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = InvalidImageError("Bad image")
            await execute_job(job, pipeline_input)

        assert job.status == JobStatus.FAILED
        assert job.failed_stage == "visual_art_historian"
        assert "Bad image" in job.error

    async def test_not_artwork_maps_to_failed_stage(self):
        from artgents.api.jobs import create_job, execute_job
        from artgents.pipeline import NotArtworkError

        job = create_job()
        pipeline_input = MagicMock()

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = NotArtworkError("Shows a person")
            await execute_job(job, pipeline_input)

        assert job.status == JobStatus.FAILED
        assert job.failed_stage == "visual_art_historian"
        assert "person" in job.error

    async def test_vertex_error_maps_to_model_call(self):
        from artgents.api.jobs import create_job, execute_job
        from artgents.clients.vertex import VertexCallError

        job = create_job()
        pipeline_input = MagicMock()

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = VertexCallError("Timeout")
            await execute_job(job, pipeline_input)

        assert job.status == JobStatus.FAILED
        assert job.failed_stage == "model_call"

    async def test_credit_exhausted_maps_to_retrieval(self):
        from artgents.api.jobs import create_job, execute_job
        from artgents.clients.parallel import CreditExhaustedError

        job = create_job()
        pipeline_input = MagicMock()

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = CreditExhaustedError("No credits")
            await execute_job(job, pipeline_input)

        assert job.status == JobStatus.FAILED
        assert job.failed_stage == "retrieval"

    async def test_successful_job_has_result(self):
        from artgents.api.jobs import create_job, execute_job

        job = create_job()
        pipeline_input = MagicMock()
        mock_result = MagicMock()

        with patch("artgents.api.jobs.run_pipeline", new_callable=AsyncMock) as mock_run, \
             patch("artgents.api.jobs.build_analyze_response") as mock_build:
            mock_run.return_value = mock_result
            mock_build.return_value = MagicMock(spec_set=["model_dump"])
            await execute_job(job, pipeline_input)

        assert job.status == JobStatus.COMPLETED
        assert job.result is not None


# ---------------------------------------------------------------------------
# TestResponseModels — unchanged (truncation/sampling logic)
# ---------------------------------------------------------------------------


class TestResponseModels:
    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def test_truncation_at_300_chars(self):
        from artgents.api.response_models import MAX_DESCRIPTION_LENGTH

        assert MAX_DESCRIPTION_LENGTH == 300

    def test_max_evidence_sample_is_8(self):
        from artgents.api.response_models import MAX_EVIDENCE_SAMPLE

        assert MAX_EVIDENCE_SAMPLE == 8
