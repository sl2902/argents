"""API routes for the Artgents application."""

from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from artgents.agents.art_historian import InvalidImageError
from artgents.api.response_models import AnalyzeResponse, build_analyze_response
from artgents.clients.parallel import CreditExhaustedError
from artgents.clients.vertex import VertexCallError
from artgents.pipeline import PipelineInput, run_pipeline

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    files: list[UploadFile] = File(..., description="Image file(s) of the artwork"),
    known_title: str | None = Form(default=None, description="Known title, if available"),
    known_artist: str | None = Form(default=None, description="Known artist, if available"),
    known_period: str | None = Form(default=None, description="Known period, if available"),
    medium: str | None = Form(default=None, description="Known medium, if available"),
    variant_key: str | None = Form(default=None, description="Curator voice variant (auction_house or public_gallery)"),
):
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
        variant_key=variant_key,
    )

    try:
        result = await run_pipeline(pipeline_input)
    except InvalidImageError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "stage": "visual_art_historian"},
        )
    except CreditExhaustedError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "stage": "retrieval"},
        )
    except VertexCallError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "stage": "model_call"},
        )
    except Exception as exc:
        logger.error("Pipeline failed with unexpected error: {}", str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "stage": "unknown"},
        )

    return build_analyze_response(result)
