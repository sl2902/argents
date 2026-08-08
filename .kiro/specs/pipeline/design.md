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
    # NOTE: no variant_key — both Curator variants are always computed,
    # per the "Reuse over re-run" principle in structure.md

class PipelineResult(BaseModel):
    visual_analysis: VisualAnalysisOutput
    title_risk: TitleRiskMatrix
    valuation: FinancialValuationResult
    curator_output_auction_house: CuratorOutput
    curator_output_public_gallery: CuratorOutput

async def run_pipeline(
    input: PipelineInput,
    on_progress: Callable[[str, str], None] | None = None,
) -> PipelineResult:
    def _report(stage_key: str, message: str) -> None:
        if on_progress is not None:
            try:
                on_progress(stage_key, message)
            except Exception:
                logger.exception("on_progress callback failed")

    def _tagged(stage_key: str) -> Callable[[str], None]:
        # Wrapper so assess_provenance()/assess_valuation()/curate()
        # each receive a plain Callable[[str], None] and don't need to
        # know about stage tagging — only run_pipeline() knows the
        # stage_key mapping.
        return lambda message: _report(stage_key, message)

    _report("start", "Starting analysis...")
    _report("visual_analysis", "Analyzing artwork...")
    visual_analysis = await analyze_artwork(VisualAnalysisInput(
        images=input.images,
        known_title=input.known_title,
        known_artist=input.known_artist,
        known_period=input.known_period,
        medium=input.medium,
    ))

    if not visual_analysis.is_artwork:
        raise NotArtworkError(visual_analysis.is_artwork_reasoning)

    _report("concurrent_research", "Researching provenance and estimating valuation...")
    title_risk, valuation = await asyncio.gather(
        assess_provenance(
            visual_analysis.search_keys,
            on_progress=_tagged("concurrent_research"),
        ),
        assess_valuation(
            visual_analysis.search_keys,
            on_progress=_tagged("concurrent_research"),
        ),
    )

    _report("curator", "Writing exhibition copy...")
    curator_auction_house, curator_public_gallery = await asyncio.gather(
        curate(CuratorInput(
            visual_analysis=visual_analysis,
            title_risk=title_risk,
            valuation=valuation,
            variant_key="auction_house",
        ), on_progress=_tagged("curator")),
        curate(CuratorInput(
            visual_analysis=visual_analysis,
            title_risk=title_risk,
            valuation=valuation,
            variant_key="public_gallery",
        ), on_progress=_tagged("curator")),
    )

    _report("curator", "Complete.")
    return PipelineResult(
        visual_analysis=visual_analysis,
        title_risk=title_risk,
        valuation=valuation,
        curator_output_auction_house=curator_auction_house,
        curator_output_public_gallery=curator_public_gallery,
    )
```

## Substep granularity — threading on_progress into agent internals

The top-level `on_progress` calls at pipeline stage boundaries (4
messages total) give an honest but coarse view — a user sees "Stage 2
running" for 25-40+ seconds with no visibility into what's actually
happening underneath. Each agent already logs at meaningful internal
points (retrieval per source, each sub-agent's completion) — threading
the SAME `on_progress` callback down into those existing log points
gives real substep granularity without inventing new instrumentation.

**Callback signature is `(stage_key: str, message: str)`, not a bare
string** — see "Progress reporting" in requirements.md for why:
reliable frontend grouping requires a real field to group by, not
message-text inference. `run_pipeline()` is the only place that knows
the stage_key mapping; it builds stage-scoped wrapper closures (e.g.
`_tagged("concurrent_research")` returning a function that calls
`on_progress("concurrent_research", msg)`) and passes those into
`assess_provenance()`, `assess_valuation()`, `curate()` — those
functions receive a plain `Callable[[str], None]` from their own
point of view and don't need to know about stage tagging at all.

Each of `assess_provenance()`, `assess_valuation()`, and `curate()`
gains an optional `on_progress: Callable[[str], None] | None`
parameter (single-string, from their perspective — the tagging happens
one level up in `run_pipeline()`), passed through from `run_pipeline()`.
Internally, each function calls it at the same points it already logs:

- `assess_provenance()` → inside `gather_evidence()`: after each
  source completes (Wikidata, Met, AIC, Parallel Search — in whatever
  order they actually complete, since these already run somewhat
  independently); then after each sub-agent completes
  (`run_compliance_auditor()`, `run_provenance_historian()`)
- `assess_valuation()` → inside `gather_comps()`: after each source
  completes (Wikidata, Parallel Search); then after each sub-agent
  completes (`run_conservative_appraiser()`, `run_bullish_specialist()`)
- `curate()` → one message per variant as each completes (not
  mid-variant substeps — Curator is a single model call per variant,
  there's no finer internal granularity to report); `run_pipeline()`
  tags these `"curator"`

This roughly triples the total message count from today's 4 to
somewhere around 12-15 real messages across a full run, all reflecting
genuine completion of real work — not fabricated.

Note the two `curate()` calls also run concurrently via
`asyncio.gather` — there's no dependency between them either, same
reasoning as stage 2.

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
INFO: Stage 3 (Curator, both variants concurrent) complete
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