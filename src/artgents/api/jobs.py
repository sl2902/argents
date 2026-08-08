"""In-memory job store for async pipeline execution.

LIMITATION: This is a single-instance, in-memory store. Jobs are lost on
server restart and not shared across multiple worker instances. This is
acceptable for a single-user hackathon demo but NOT suitable for
production multi-instance deployment. A persistent job store (Redis, DB)
would be needed for that.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

from artgents.agents.art_historian import InvalidImageError
from artgents.api.cache import compute_cache_key, get_cached, set_cached
from artgents.api.response_models import AnalyzeResponse, build_analyze_response
from artgents.clients.parallel import CreditExhaustedError
from artgents.clients.vertex import VertexCallError
from artgents.pipeline import NotArtworkError, PipelineInput, run_pipeline


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProgressEntry:
    stage_key: str
    message: str


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.PENDING
    logs: list[ProgressEntry] = field(default_factory=list)
    result: AnalyzeResponse | None = None
    error: str | None = None
    failed_stage: str | None = None


# In-memory job store — single-instance only (see module docstring)
JOBS: dict[str, Job] = {}


def create_job() -> Job:
    """Create a new pending job and register it in the store."""
    job = Job(id=str(uuid.uuid4()))
    JOBS[job.id] = job
    return job


async def execute_job(job: Job, pipeline_input: PipelineInput) -> None:
    """Run the pipeline in the background, updating job status as it progresses.

    Checks the response cache first — a hit short-circuits to COMPLETED with
    no pipeline execution. On a cache miss, runs normally and caches the result
    only on successful completion (never on any failure path).
    """
    job.status = JobStatus.RUNNING

    # --- Cache check (before any real work) ---
    cache_key = compute_cache_key(
        pipeline_input.images,
        pipeline_input.known_title,
        pipeline_input.known_artist,
        pipeline_input.known_period,
        pipeline_input.medium,
    )
    cached = get_cached(cache_key)
    if cached is not None:
        job.result = cached
        job.status = JobStatus.COMPLETED
        job.logs.append(ProgressEntry(stage_key="cache", message="Loaded from cache."))
        logger.info("Job {} served from cache (key={})", job.id, cache_key[:12])
        return

    # --- Cache miss: run pipeline normally ---
    job.logs.append(ProgressEntry(stage_key="start", message="Starting analysis..."))

    def on_progress(stage_key: str, msg: str) -> None:
        job.logs.append(ProgressEntry(stage_key=stage_key, message=msg))

    try:
        pipeline_result = await run_pipeline(pipeline_input, on_progress=on_progress)
        job.result = build_analyze_response(pipeline_result)
        job.status = JobStatus.COMPLETED
        set_cached(cache_key, job.result)
        logger.info("Job {} completed and cached (key={})", job.id, cache_key[:12])

    except InvalidImageError as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.failed_stage = "visual_art_historian"
        logger.error("Job {} failed (invalid image): {}", job.id, exc)

    except NotArtworkError as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.failed_stage = "visual_art_historian"
        logger.warning("Job {} rejected (not artwork): {}", job.id, exc)

    except CreditExhaustedError as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.failed_stage = "retrieval"
        logger.error("Job {} failed (credits): {}", job.id, exc)

    except VertexCallError as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.failed_stage = "model_call"
        logger.error("Job {} failed (vertex): {}", job.id, exc)

    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.failed_stage = "unknown"
        logger.error("Job {} failed (unexpected): {}", job.id, exc)
