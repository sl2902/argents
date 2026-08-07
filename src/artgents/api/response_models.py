"""Response models for the Artgents API.

Transforms internal PipelineResult into a flat, frontend-friendly shape
with truncated evidence samples and timing data.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from artgents.agents.financial_valuation import (
    BullishSpecialistOutput,
    ConservativeAppraiserOutput,
    ValuationCorridor,
)
from artgents.agents.provenance_legal import (
    ComplianceAuditorOutput,
    ProvenanceHistorianOutput,
)


class StageTimings(BaseModel):
    visual_analysis_ms: int
    stage_2_wall_clock_ms: int
    provenance_ms: int
    valuation_ms: int
    curator_ms: int
    total_ms: int


class EvidenceItemDisplay(BaseModel):
    description: str  # truncated to ~300 chars
    source_url: str
    source_type: str


class AnalyzeResponse(BaseModel):
    # Visual analysis
    attribution: str
    period_style: str
    composition_analysis: str
    condition_notes: str
    stylistic_authenticity_notes: str

    # Provenance - both sub-agents
    compliance_auditor: ComplianceAuditorOutput
    provenance_historian: ProvenanceHistorianOutput
    provenance_synthesis_summary: str
    provenance_requires_human_review: bool

    # Valuation - both sub-agents
    conservative_appraiser: ConservativeAppraiserOutput
    bullish_specialist: BullishSpecialistOutput
    valuation_corridor: ValuationCorridor
    corridor_summary: str
    valuation_requires_human_review: bool

    # Curator
    exhibition_narrative: str
    wall_label: str
    suggested_title: str
    disclosures: list[str]
    variant_used: str

    # Evidence sample
    provenance_evidence_sample: list[EvidenceItemDisplay]
    valuation_evidence_sample: list[EvidenceItemDisplay]
    total_provenance_facts: int
    total_valuation_comps: int

    # Timing
    timings: StageTimings


class ErrorResponse(BaseModel):
    error: str
    stage: str


MAX_EVIDENCE_SAMPLE = 8
MAX_DESCRIPTION_LENGTH = 300


def build_analyze_response(pipeline_result) -> AnalyzeResponse:
    """Transform PipelineResult into the API response shape.

    Truncates evidence text, samples entries, computes timing —
    NEVER mutates the underlying PipelineResult.
    """
    r = pipeline_result

    # Evidence sampling + truncation
    prov_facts = r.title_risk.evidence_bundle.retrieved_facts
    val_comps = r.valuation.evidence.comparable_sales

    def truncate(text: str) -> str:
        if len(text) > MAX_DESCRIPTION_LENGTH:
            return text[: MAX_DESCRIPTION_LENGTH - 3] + "..."
        return text

    prov_sample = [
        EvidenceItemDisplay(
            description=truncate(f.claim),
            source_url=f.source_url,
            source_type=f.source_type,
        )
        for f in prov_facts[:MAX_EVIDENCE_SAMPLE]
    ]

    val_sample = [
        EvidenceItemDisplay(
            description=truncate(f.description),
            source_url=f.source_url,
            source_type=f.source_type,
        )
        for f in val_comps[:MAX_EVIDENCE_SAMPLE]
    ]

    # Build timings
    t = r.timings
    timings = StageTimings(
        visual_analysis_ms=t.visual_analysis_ms if t else 0,
        stage_2_wall_clock_ms=t.stage_2_wall_clock_ms if t else 0,
        provenance_ms=t.provenance_ms if t else 0,
        valuation_ms=t.valuation_ms if t else 0,
        curator_ms=t.curator_ms if t else 0,
        total_ms=t.total_ms if t else 0,
    )

    return AnalyzeResponse(
        attribution=r.visual_analysis.search_keys.primary_artist_attribution,
        period_style=f"{r.visual_analysis.search_keys.probable_creation_window}, {r.visual_analysis.search_keys.style_and_movement}",
        composition_analysis=r.visual_analysis.composition_analysis,
        condition_notes=r.visual_analysis.condition_notes,
        stylistic_authenticity_notes=r.visual_analysis.stylistic_authenticity_notes,
        compliance_auditor=r.title_risk.compliance_auditor,
        provenance_historian=r.title_risk.provenance_historian,
        provenance_synthesis_summary=r.title_risk.synthesis_summary,
        provenance_requires_human_review=r.title_risk.requires_human_review,
        conservative_appraiser=r.valuation.conservative_appraiser,
        bullish_specialist=r.valuation.bullish_specialist,
        valuation_corridor=r.valuation.valuation_corridor,
        corridor_summary=r.valuation.corridor_summary,
        valuation_requires_human_review=r.valuation.requires_human_review,
        exhibition_narrative=r.curator_output.exhibition_narrative,
        wall_label=r.curator_output.wall_label,
        suggested_title=r.curator_output.suggested_title,
        disclosures=r.curator_output.disclosures,
        variant_used=r.curator_output.variant_used,
        provenance_evidence_sample=prov_sample,
        valuation_evidence_sample=val_sample,
        total_provenance_facts=len(prov_facts),
        total_valuation_comps=len(val_comps),
        timings=timings,
    )
