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

from loguru import logger
from pydantic import BaseModel, Field

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
        VertexCallError: If any Vertex AI call fails.
        CreditExhaustedError: If Parallel Search credits are exhausted.
    """
    pipeline_start = time.perf_counter()
    logger.info("Pipeline started")

    # --- Stage 1: Visual Art Historian ---
    logger.info("Stage 1: Visual Art Historian — starting")
    visual_analysis = await analyze_artwork(
        VisualAnalysisInput(
            images=input_data.images,
            known_title=input_data.known_title,
            known_artist=input_data.known_artist,
            known_period=input_data.known_period,
            medium=input_data.medium,
        )
    )
    logger.info(
        "Stage 1: Visual Art Historian — complete (attribution={})",
        visual_analysis.search_keys.primary_artist_attribution,
    )

    # --- Stage 2: Provenance/Legal + Financial Valuation (concurrent) ---
    logger.info("Stage 2: Provenance/Legal + Financial Valuation — starting (concurrent)")
    title_risk, valuation = await asyncio.gather(
        assess_provenance(visual_analysis.search_keys),
        assess_valuation(visual_analysis.search_keys),
    )
    logger.info(
        "Stage 2: concurrent stage complete (provenance_review={}, valuation_review={})",
        title_risk.requires_human_review,
        valuation.requires_human_review,
    )

    # --- Stage 3: Curator ---
    logger.info("Stage 3: Curator — starting")
    curator_output = await curate(
        CuratorInput.model_construct(
            visual_analysis=visual_analysis,
            title_risk=title_risk,
            valuation=valuation,
            variant_key=input_data.variant_key,
        )
    )
    logger.info(
        "Stage 3: Curator — complete (variant={})",
        curator_output.variant_used,
    )

    elapsed_s = time.perf_counter() - pipeline_start
    logger.info("Pipeline complete in {:.1f}s", elapsed_s)

    return PipelineResult.model_construct(
        visual_analysis=visual_analysis,
        title_risk=title_risk,
        valuation=valuation,
        curator_output=curator_output,
    )
