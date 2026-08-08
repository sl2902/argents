"""API routes for the Artgents application."""

from __future__ import annotations

import asyncio
import base64

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from artgents.api.jobs import JOBS, Job, JobStatus, create_job, execute_job
from artgents.api.response_models import AnalyzeResponse
from artgents.pipeline import PipelineInput

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/analyze")
async def analyze(
    files: list[UploadFile] = File(..., description="Image file(s) of the artwork"),
    known_title: str | None = Form(default=None, description="Known title, if available"),
    known_artist: str | None = Form(default=None, description="Known artist, if available"),
    known_period: str | None = Form(default=None, description="Known period, if available"),
    medium: str | None = Form(default=None, description="Known medium, if available"),
):
    """Start an analysis job. Returns immediately with a job_id for polling."""
    # Convert uploaded files to base64
    images = []
    for file in files:
        content = await file.read()
        images.append(base64.b64encode(content).decode())

    if not images:
        return JSONResponse(
            status_code=400,
            content={"error": "No images uploaded", "stage": "upload"},
        )

    pipeline_input = PipelineInput(
        images=images,
        known_title=known_title,
        known_artist=known_artist,
        known_period=known_period,
        medium=medium,
    )

    # Create job and start background execution
    job = create_job()
    asyncio.create_task(execute_job(job, pipeline_input))

    return {"job_id": job.id}


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """Poll job status. Returns current progress, and result when complete."""
    job = JOBS.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})

    response: dict = {
        "job_id": job.id,
        "status": job.status.value,
        "logs": [{"stage_key": e.stage_key, "message": e.message} for e in job.logs],
    }

    if job.status == JobStatus.COMPLETED and job.result:
        response["result"] = job.result.model_dump()
    elif job.status == JobStatus.FAILED:
        response["error"] = job.error
        response["failed_stage"] = job.failed_stage

    return response
