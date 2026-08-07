# Design: API Layer

## Architecture

```
POST /api/analyze (multipart)
        │
        ▼
┌────────────────────────────┐
│ api/routes.py               │
│  - parse multipart, build   │
│    PipelineInput             │
│  - call run_pipeline()       │
│  - shape response (truncate  │
│    evidence text, compute    │
│    timing breakdown)         │
│  - map errors to HTTP status │
└────────────────────────────┘
        │
        ▼
  AnalyzeResponse (JSON)
```

## File layout

```
src/artgents/
├── api/
│   ├── __init__.py
│   ├── app.py              # FastAPI app instance, CORS config
│   ├── routes.py           # /api/analyze, /api/health
│   └── response_models.py  # AnalyzeResponse and nested shapes
```

## Response models

```python
# src/artgents/api/response_models.py

class SubAgentTimingBreakdown(BaseModel):
    stage_name: str
    duration_ms: int

class StageTimings(BaseModel):
    visual_analysis_ms: int
    stage_2_wall_clock_ms: int  # actual elapsed time for stage 2
                                  # (concurrent) — the number that
                                  # demonstrates parallelism
    provenance_ms: int          # provenance/legal's own duration
    valuation_ms: int           # financial valuation's own duration
    curator_ms: int
    total_ms: int

class EvidenceItemDisplay(BaseModel):
    description: str  # truncated for display
    source_url: str
    source_type: str

class AnalyzeResponse(BaseModel):
    # Visual analysis
    attribution: str
    period_style: str
    composition_analysis: str
    condition_notes: str
    stylistic_authenticity_notes: str

    # Provenance — both sub-agents, not just synthesis
    compliance_auditor: ComplianceAuditorOutput
    provenance_historian: ProvenanceHistorianOutput
    provenance_synthesis_summary: str
    provenance_requires_human_review: bool

    # Valuation — both sub-agents
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
    total_provenance_facts: int  # full count, even if sample is smaller
    total_valuation_comps: int

    # Timing
    timings: StageTimings
```

Reuses the existing Pydantic sub-models (`ComplianceAuditorOutput`,
`ProvenanceHistorianOutput`, etc.) directly from their agent modules
rather than redefining them — no duplication of schema.

## Timing capture

`run_pipeline()` itself (per the pipeline spec) already logs
stage-transition timestamps but doesn't currently return them as data.
Extend `PipelineResult` (or wrap it) to also capture timestamps at each
stage boundary, so the API layer can compute `StageTimings` without
re-deriving it from log parsing. This is a small addition to
`pipeline.py`, not a new concept — the logging already proves the
timing exists, this just captures it as structured data too.

## Evidence sampling and truncation

- Sample: take the first N (e.g. 5-8) entries from
  `retrieved_facts`/`comparable_sales` for the response, not all 40-56
  — full counts still reported via `total_provenance_facts`/
  `total_valuation_comps` so the UI can show "5 of 44 sources shown."
- Truncation: `description`/`claim` text cut to ~300 chars with an
  ellipsis if longer; `source_url` never truncated.
- This happens ONLY in `response_models.py`'s construction from
  `PipelineResult` — the underlying `PipelineResult`/agent outputs are
  never mutated.

## Error handling

```python
@app.exception_handler(InvalidImageError)
async def handle_invalid_image(request, exc):
    return JSONResponse(status_code=400, content={"error": str(exc), "stage": "visual_art_historian"})

# similar handlers per typed error, identifying the stage
```

Map each agent's typed exceptions to appropriate HTTP status codes with
a `stage` field identifying where the failure occurred — consistent
with the pipeline's own "no silent partial success" scope decision.

## CORS

Permissive dev default (`allow_origins=["*"]` or localhost-specific)
for now; note in code comments that this should be tightened to the
actual frontend origin before final submission if time allows.

## Testing approach

- Unit tests: `response_models.py` construction from a mocked
  `PipelineResult` — verify truncation, sampling, timing shape are all
  correct
- Unit tests: error handlers map each typed exception to the correct
  status code and stage field
- Integration test (marked separately): real `POST /api/analyze` call
  with an actual image via FastAPI's test client, against the real
  pipeline