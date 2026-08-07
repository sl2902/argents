"""Artgents pipeline — single-call orchestration of all four agents.

Execution order:
1. Visual Art Historian → VisualAnalysisOutput (search_keys)
2. Provenance/Legal + Financial Valuation → CONCURRENT via asyncio.gather
3. Curator → CuratorOutput (final synthesis)

Errors propagate naturally — no try/except suppression. If any stage
fails outright, the whole pipeline fails with a clear, typed error.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from loguru import logger
from pydantic import BaseModel, Field


class NotArtworkError(Exception):
    """Raised when the uploaded image is not a physical artwork.

    The pipeline stops immediately — no downstream agents are invoked.
    """

    pass

from artgents.agents.art_historian import (
    VisualAnalysisInput,
    VisualAnalysisOutput,
    analyze_artwork,
)
from artgents.agents.curator import (
    CuratorInput,
    CuratorOutput,
    curate,
)
from artgents.agents.financial_valuation import (
    FinancialValuationResult,
    assess_valuation,
)
from artgents.agents.provenance_legal import (
    TitleRiskMatrix,
    assess_provenance,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class StageTiming:
    """Timing data for each pipeline stage (milliseconds)."""

    visual_analysis_ms: int = 0
    provenance_ms: int = 0
    valuation_ms: int = 0
    stage_2_wall_clock_ms: int = 0  # actual elapsed for concurrent stage
    curator_ms: int = 0
    total_ms: int = 0


class PipelineInput(BaseModel):
    """Input for the full Artgents pipeline."""

    images: list[str] = Field(
        ..., min_length=1, description="Base64-encoded image(s) of the artwork"
    )
    known_title: str | None = Field(default=None, description="Known title, if available")
    known_artist: str | None = Field(default=None, description="Known artist, if available")
    known_period: str | None = Field(default=None, description="Known period, if available")
    medium: str | None = Field(default=None, description="Known medium, if available")
    variant_key: str | None = Field(
        default=None, description="Curator voice variant (None → YAML default)"
    )


class PipelineResult(BaseModel):
    """Complete result from a full pipeline run.

    Exposes all intermediate agent outputs alongside the final CuratorOutput,
    so inspectors can see the actual evidence/reasoning behind the narrative.
    """

    model_config = {"arbitrary_types_allowed": True}

    visual_analysis: VisualAnalysisOutput
    title_risk: TitleRiskMatrix
    valuation: FinancialValuationResult
    curator_output: CuratorOutput
    timings: StageTiming | None = None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_pipeline(input_data: PipelineInput) -> PipelineResult:
    """Execute the full Artgents pipeline end-to-end.

    Stages:
    1. Visual Art Historian (sequential — required for all downstream stages)
    2. Provenance/Legal + Financial Valuation (concurrent via asyncio.gather)
    3. Curator (sequential — requires all prior outputs)

    Errors propagate naturally — no suppression. If any stage fails,
    the pipeline fails with a clear, typed error.

    Args:
        input_data: Image(s) + optional metadata + variant selection.

    Returns:
        PipelineResult with all four agents' outputs.

    Raises:
        InvalidImageError: If the image is invalid (from Visual Art Historian).
        NotArtworkError: If the image is not a physical artwork.
        VertexCallError: If any Vertex AI call fails.
        CreditExhaustedError: If Parallel Search credits are exhausted.
    """
    pipeline_start = time.perf_counter()
    logger.info("Pipeline started")

    # --- Stage 1: Visual Art Historian ---
    logger.info("Stage 1: Visual Art Historian — starting")
    stage1_start = time.perf_counter()
    visual_analysis = await analyze_artwork(
        VisualAnalysisInput(
            images=input_data.images,
            known_title=input_data.known_title,
            known_artist=input_data.known_artist,
            known_period=input_data.known_period,
            medium=input_data.medium,
        )
    )
    visual_analysis_ms = int((time.perf_counter() - stage1_start) * 1000)
    logger.info(
        "Stage 1: Visual Art Historian — complete (attribution={}, {}ms)",
        visual_analysis.search_keys.primary_artist_attribution,
        visual_analysis_ms,
    )

    # --- Gate check: is this actually an artwork? ---
    if not visual_analysis.is_artwork:
        logger.warning(
            "Pipeline stopped: image is not an artwork — {}",
            visual_analysis.is_artwork_reasoning,
        )
        raise NotArtworkError(visual_analysis.is_artwork_reasoning)

    # --- Stage 2: Provenance/Legal + Financial Valuation (concurrent) ---
    logger.info("Stage 2: Provenance/Legal + Financial Valuation — starting (concurrent)")

    async def _timed_provenance(search_keys):
        start = time.perf_counter()
        result = await assess_provenance(search_keys)
        return result, int((time.perf_counter() - start) * 1000)

    async def _timed_valuation(search_keys):
        start = time.perf_counter()
        result = await assess_valuation(search_keys)
        return result, int((time.perf_counter() - start) * 1000)

    stage2_start = time.perf_counter()
    (title_risk, prov_ms), (valuation, val_ms) = await asyncio.gather(
        _timed_provenance(visual_analysis.search_keys),
        _timed_valuation(visual_analysis.search_keys),
    )
    stage_2_wall_clock_ms = int((time.perf_counter() - stage2_start) * 1000)
    logger.info(
        "Stage 2: concurrent stage complete (provenance_review={}, valuation_review={}, "
        "wall_clock={}ms, prov={}ms, val={}ms)",
        title_risk.requires_human_review,
        valuation.requires_human_review,
        stage_2_wall_clock_ms,
        prov_ms,
        val_ms,
    )

    # --- Stage 3: Curator ---
    logger.info("Stage 3: Curator — starting")
    stage3_start = time.perf_counter()
    curator_output = await curate(
        CuratorInput.model_construct(
            visual_analysis=visual_analysis,
            title_risk=title_risk,
            valuation=valuation,
            variant_key=input_data.variant_key,
        )
    )
    curator_ms = int((time.perf_counter() - stage3_start) * 1000)
    logger.info(
        "Stage 3: Curator — complete (variant={}, {}ms)",
        curator_output.variant_used,
        curator_ms,
    )

    total_ms = int((time.perf_counter() - pipeline_start) * 1000)
    logger.info("Pipeline complete in {:.1f}s", total_ms / 1000)

    timings = StageTiming(
        visual_analysis_ms=visual_analysis_ms,
        provenance_ms=prov_ms,
        valuation_ms=val_ms,
        stage_2_wall_clock_ms=stage_2_wall_clock_ms,
        curator_ms=curator_ms,
        total_ms=total_ms,
    )

    return PipelineResult.model_construct(
        visual_analysis=visual_analysis,
        title_risk=title_risk,
        valuation=valuation,
        curator_output=curator_output,
        timings=timings,
    )
