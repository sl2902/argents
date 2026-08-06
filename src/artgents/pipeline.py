"""Artgents pipeline — sequences agent calls in the correct order.

Execution order (sequential, not fan-out):
1. Visual Art Historian → produces VisualAnalysisOutput
   - search_keys available for stage 2
2. Provenance/Legal agent → uses search_keys to query external sources
3. Financial Valuation agent → uses provenance + visual data
4. Curator agent → synthesizes all prior agent outputs into exhibition copy

This module is the ONLY place that sequences agent calls. Agents do not
call each other directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from artgents.agents.art_historian import (
    InvalidImageError,
    VisualAnalysisInput,
    VisualAnalysisOutput,
    analyze_artwork,
)
from artgents.clients.vertex import VertexCallError


@dataclass
class PipelineResult:
    """Accumulated results from a pipeline run.

    Each agent's output is stored separately so downstream consumers
    can access exactly what they need.
    """

    visual_analysis: VisualAnalysisOutput | None = None
    provenance_legal: Any = None  # TODO: type once Provenance/Legal spec exists
    financial_valuation: Any = None  # TODO: type once Financial Valuation spec exists
    curator_output: Any = None  # TODO: type once Curator spec exists
    errors: list[str] = field(default_factory=list)


async def run_pipeline(input_data: VisualAnalysisInput) -> PipelineResult:
    """Execute the full Artgents pipeline.

    Runs agents sequentially — each stage depends on the previous stage's
    output. If an early stage fails, the pipeline records the error and
    returns partial results.

    Args:
        input_data: Image (base64) and optional metadata for the artwork.

    Returns:
        PipelineResult with each agent's output (or None if that stage failed).
    """
    result = PipelineResult()

    # --- Stage 1: Visual Art Historian ---
    logger.info("Pipeline stage 1: Visual Art Historian")
    try:
        result.visual_analysis = await analyze_artwork(input_data)
        logger.info(
            "Stage 1 complete: search_keys.primary_artist_attribution={}",
            result.visual_analysis.search_keys.primary_artist_attribution,
        )
    except InvalidImageError as exc:
        logger.error("Pipeline aborted at stage 1: invalid image — {}", str(exc))
        result.errors.append(f"Visual Art Historian: {exc}")
        return result
    except VertexCallError as exc:
        logger.error("Pipeline stage 1 failed: Vertex AI error — {}", str(exc))
        result.errors.append(f"Visual Art Historian: {exc}")
        return result

    # --- Stage 2: Provenance/Legal ---
    # TODO: Implement once provenance_legal agent spec exists.
    # Will consume result.visual_analysis.search_keys
    logger.info(
        "Pipeline stage 2: Provenance/Legal (not yet implemented — "
        "search_keys available for handoff)"
    )

    # --- Stage 3: Financial Valuation ---
    # TODO: Implement once financial_valuation agent spec exists.
    logger.info("Pipeline stage 3: Financial Valuation (not yet implemented)")

    # --- Stage 4: Curator ---
    # TODO: Implement once curator agent spec exists.
    # Will consume: visual_analysis, provenance_legal, financial_valuation
    logger.info("Pipeline stage 4: Curator (not yet implemented)")

    return result
