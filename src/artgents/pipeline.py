"""Artgents pipeline — single-call orchestration of all four agents.

Execution order:
1. Visual Art Historian → VisualAnalysisOutput (search_keys)
2. Provenance/Legal + Financial Valuation → CONCURRENT via asyncio.gather
3. Curator (both variants) → CONCURRENT via asyncio.gather

Errors propagate naturally — no try/except suppression. If any stage
fails outright, the whole pipeline fails with a clear, typed error.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable

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
    stage_2_wall_clock_ms: int = 0
    curator_ms: int = 0  # wall-clock for both variants (concurrent)
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


class PipelineResult(BaseModel):
    """Complete result from a full pipeline run.

    Exposes all intermediate agent outputs alongside BOTH Curator variants,
    so inspectors can see the actual evidence/reasoning behind the narrative.
    Both variants reuse the same upstream findings — no re-run needed.
    """

    model_config = {"arbitrary_types_allowed": True}

    visual_analysis: VisualAnalysisOutput
    title_risk: TitleRiskMatrix
    valuation: FinancialValuationResult
    curator_output_auction_house: CuratorOutput
    curator_output_public_gallery: CuratorOutput
    timings: StageTiming | None = None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_pipeline(
    input_data: PipelineInput,
    on_progress: "Callable[[str, str], None] | None" = None,
) -> PipelineResult:
    """Execute the full Artgents pipeline end-to-end.

    Stages:
    1. Visual Art Historian (sequential — required for all downstream stages)
    2. Provenance/Legal + Financial Valuation (concurrent via asyncio.gather)
    3. Curator — both variants (concurrent via asyncio.gather, reusing same upstream)

    Errors propagate naturally — no suppression. If any stage fails,
    the pipeline fails with a clear, typed error.

    Args:
        input_data: Image(s) + optional metadata.
        on_progress: Optional callback invoked at each stage transition
            with a human-readable progress message. Exceptions in the
            callback are caught and logged, never propagated.

    Returns:
        PipelineResult with all agents' outputs (both Curator variants).

    Raises:
        InvalidImageError: If the image is invalid (from Visual Art Historian).
        NotArtworkError: If the image is not a physical artwork.
        VertexCallError: If any Vertex AI call fails.
        CreditExhaustedError: If Parallel Search credits are exhausted.
    """
    def _progress(stage_key: str, msg: str) -> None:
        if on_progress:
            try:
                on_progress(stage_key, msg)
            except Exception as exc:
                logger.debug("on_progress callback error (ignored): {}", exc)

    def _tagged(stage_key: str):
        """Return a Callable[[str], None] that tags messages with stage_key."""
        def _cb(msg: str) -> None:
            _progress(stage_key, msg)
        return _cb

    pipeline_start = time.perf_counter()
    logger.info("Pipeline started")

    # --- Stage 1: Visual Art Historian ---
    _progress("visual_analysis", "Analyzing artwork...")
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
    _progress("concurrent_research", "Researching provenance and valuing artwork (running concurrently)...")
    logger.info("Stage 2: Provenance/Legal + Financial Valuation — starting (concurrent)")

    async def _timed_provenance(search_keys):
        start = time.perf_counter()
        result = await assess_provenance(search_keys, on_progress=_tagged("concurrent_research"))
        return result, int((time.perf_counter() - start) * 1000)

    async def _timed_valuation(search_keys):
        start = time.perf_counter()
        result = await assess_valuation(search_keys, on_progress=_tagged("concurrent_research"))
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

    # --- Stage 3: Curator — both variants (concurrent) ---
    _progress("curator", "Writing exhibition copy...")
    logger.info("Stage 3: Curator — starting (both variants, concurrent)")
    stage3_start = time.perf_counter()

    curator_auction_house, curator_public_gallery = await asyncio.gather(
        curate(CuratorInput.model_construct(
            visual_analysis=visual_analysis,
            title_risk=title_risk,
            valuation=valuation,
            variant_key="auction_house",
        ), on_progress=_tagged("curator")),
        curate(CuratorInput.model_construct(
            visual_analysis=visual_analysis,
            title_risk=title_risk,
            valuation=valuation,
            variant_key="public_gallery",
        ), on_progress=_tagged("curator")),
    )

    curator_ms = int((time.perf_counter() - stage3_start) * 1000)
    logger.info("Stage 3: Curator — complete (both variants, {}ms)", curator_ms)

    total_ms = int((time.perf_counter() - pipeline_start) * 1000)
    logger.info("Pipeline complete in {:.1f}s", total_ms / 1000)
    _progress("curator", "Analysis complete.")

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
        curator_output_auction_house=curator_auction_house,
        curator_output_public_gallery=curator_public_gallery,
        timings=timings,
    )
