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

from loguru import logger

from artgents.agents.art_historian import (
    InvalidImageError,
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
from artgents.clients.parallel import CreditExhaustedError
from artgents.clients.vertex import VertexCallError


@dataclass
class PipelineResult:
    """Accumulated results from a pipeline run.

    Each agent's output is stored separately so downstream consumers
    can access exactly what they need.
    """

    visual_analysis: VisualAnalysisOutput | None = None
    provenance_legal: TitleRiskMatrix | None = None
    financial_valuation: FinancialValuationResult | None = None
    curator_output: CuratorOutput | None = None
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
    logger.info("Pipeline stage 2: Provenance/Legal")
    try:
        result.provenance_legal = await assess_provenance(
            result.visual_analysis.search_keys
        )
        logger.info(
            "Stage 2 complete: requires_human_review={}",
            result.provenance_legal.requires_human_review,
        )
    except CreditExhaustedError as exc:
        logger.error(
            "Pipeline stage 2: Parallel Search credits exhausted — {}", str(exc)
        )
        result.errors.append(f"Provenance/Legal: {exc}")
        # Continue — partial pipeline results are still useful
    except VertexCallError as exc:
        logger.error("Pipeline stage 2 failed: Vertex AI error — {}", str(exc))
        result.errors.append(f"Provenance/Legal: {exc}")
        # Continue — stage 3/4 can still run with whatever is available

    # --- Stage 3: Financial Valuation ---
    logger.info("Pipeline stage 3: Financial Valuation")
    try:
        result.financial_valuation = await assess_valuation(
            result.visual_analysis.search_keys,
            title_risk=result.provenance_legal,
        )
        logger.info(
            "Stage 3 complete: corridor=${:,.0f}–${:,.0f}",
            result.financial_valuation.valuation_corridor.low_estimate_usd,
            result.financial_valuation.valuation_corridor.high_estimate_usd,
        )
    except CreditExhaustedError as exc:
        logger.error(
            "Pipeline stage 3: Parallel Search credits exhausted — {}", str(exc)
        )
        result.errors.append(f"Financial Valuation: {exc}")
    except VertexCallError as exc:
        logger.error("Pipeline stage 3 failed: Vertex AI error — {}", str(exc))
        result.errors.append(f"Financial Valuation: {exc}")

    # --- Stage 4: Curator ---
    logger.info("Pipeline stage 4: Curator")
    if result.visual_analysis and result.provenance_legal and result.financial_valuation:
        try:
            curator_input = CuratorInput(
                visual_analysis=result.visual_analysis,
                title_risk=result.provenance_legal,
                valuation=result.financial_valuation,
            )
            result.curator_output = await curate(curator_input)
            logger.info(
                "Stage 4 complete: variant_used={}, disclosures={}",
                result.curator_output.variant_used,
                len(result.curator_output.disclosures),
            )
        except VertexCallError as exc:
            logger.error("Pipeline stage 4 failed: Vertex AI error — {}", str(exc))
            result.errors.append(f"Curator: {exc}")
    else:
        logger.warning(
            "Pipeline stage 4: Curator skipped — missing upstream outputs "
            "(visual={}, provenance={}, valuation={})",
            result.visual_analysis is not None,
            result.provenance_legal is not None,
            result.financial_valuation is not None,
        )

    return result
