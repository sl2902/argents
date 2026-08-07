# Design: Pipeline Orchestration

## Architecture

```
PipelineInput
        │
        ▼
  analyze_artwork()  [Visual Art Historian]
        │
        │  search_keys
        ▼
   asyncio.gather(
        assess_provenance(search_keys),
        assess_valuation(search_keys),
   )
        │
        │  title_risk, valuation
        ▼
   curate(CuratorInput(
       visual_analysis=..., title_risk=..., valuation=...,
       variant_key=...
   ))
        │
        ▼
  PipelineResult
```

## Interface

```python
# src/artgents/pipeline.py

class PipelineInput(BaseModel):
    images: list[str]  # base64
    known_title: str | None = None
    known_artist: str | None = None
    known_period: str | None = None
    medium: str | None = None
    variant_key: str | None = None  # Curator voice selection

class PipelineResult(BaseModel):
    visual_analysis: VisualAnalysisOutput
    title_risk: TitleRiskMatrix
    valuation: FinancialValuationResult
    curator_output: CuratorOutput

async def run_pipeline(input: PipelineInput) -> PipelineResult:
    visual_analysis = await analyze_artwork(VisualAnalysisInput(
        images=input.images,
        known_title=input.known_title,
        known_artist=input.known_artist,
        known_period=input.known_period,
        medium=input.medium,
    ))

    title_risk, valuation = await asyncio.gather(
        assess_provenance(visual_analysis.search_keys),
        assess_valuation(visual_analysis.search_keys),
    )

    curator_output = await curate(CuratorInput(
        visual_analysis=visual_analysis,
        title_risk=title_risk,
        valuation=valuation,
        variant_key=input.variant_key,
    ))

    return PipelineResult(
        visual_analysis=visual_analysis,
        title_risk=title_risk,
        valuation=valuation,
        curator_output=curator_output,
    )
```

## Error handling

No try/except wrapping inside `run_pipeline()` beyond what's needed for
logging — let exceptions from any stage propagate naturally as typed
errors (each agent already raises typed errors internally, e.g.
`InvalidImageError`, `ImageUnavailableError`). `run_pipeline()`'s job is
orchestration and logging, not error suppression. This matches the
"Error handling — explicit scope decision" in requirements.md: total
failure of any stage fails the whole request.

## Logging

Log at INFO on entry to each stage and on successful completion, with
enough context to reconstruct a full run's timeline from logs alone —
consistent with the granularity already present in each individual
agent (e.g. `_retrieve_wikidata`, `run_compliance_auditor` already log
their own start/completion). `run_pipeline()` adds the top-level
stage-transition view on top of that, not a replacement for it:

```
INFO: Pipeline started
INFO: Stage 1 (Visual Art Historian) complete
INFO: Stage 2 (Provenance/Legal + Financial Valuation, concurrent) complete
INFO: Stage 3 (Curator) complete
INFO: Pipeline complete
```

## Testing approach

- Unit tests: mock all four agent functions (`analyze_artwork`,
  `assess_provenance`, `assess_valuation`, `curate`). Assert:
  - Correct call order (Visual Art Historian first, Curator last)
  - `assess_provenance` and `assess_valuation` are actually concurrent
    — assert via mock timing (e.g. both mocks have an artificial
    `asyncio.sleep`, and total elapsed time is close to the single
    delay, not the sum of both) or via an in-flight-simultaneously
    assertion
  - `PipelineResult` correctly aggregates all four agents' outputs
  - An exception from any stage propagates out of `run_pipeline()`
    rather than being swallowed
- One integration test (marked separately): a full real run with one
  actual image, asserting a valid `PipelineResult` comes back — this is
  the test that actually closes Curator's task 13 acceptance bar