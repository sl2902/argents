# Requirements: Pipeline Orchestration

## Purpose

Wire the four agents into a single, callable orchestration function
that takes raw user input (image + optional known metadata) and
returns a complete `CuratorOutput`, running the agents in the correct
order with the correct concurrency.

This is the layer FastAPI endpoints will call later — it has no HTTP
concerns of its own, and must be independently testable via a plain
Python script the same way each individual agent has been throughout
this project.

## Pipeline order and concurrency

```
analyze_artwork()  [Visual Art Historian]
        │
        ├──► assess_provenance()   ┐
        │                          ├─ run CONCURRENTLY
        └──► assess_valuation()    ┘   (asyncio.gather)
                    │
                    ▼
       curate(variant="auction_house")
       curate(variant="public_gallery")
```

`assess_provenance()` and `assess_valuation()` both depend only on
Visual Art Historian's `search_keys` output, not on each other — they
must run concurrently via `asyncio.gather`, not sequentially, since
there's no data dependency between them and sequential execution would
roughly double end-to-end latency for no benefit (each individual call
already takes 15-40+ seconds based on testing).

`curate()` runs last and requires the outputs of all three prior
stages. **Per the "Reuse over re-run" principle in `structure.md`**:
`variant_key` only affects Curator, not any upstream stage, so
`run_pipeline()` computes BOTH Curator variants in one execution —
`curate()` is called twice (auction_house, public_gallery), reusing the
same `visual_analysis`/`title_risk`/`valuation` from the single
upstream run. There is no `variant_key` input to the pipeline anymore;
both outputs are always produced and returned together, and the caller
(API/frontend) picks which to display without any additional request.

## User stories

1. As a developer, I call one function with an image and get back a
   complete curated result — I don't manually chain four separate agent
   calls myself, the way manual testing has required throughout
   development so far.

2. As someone running the eventual FastAPI/frontend layer, I get a
   single well-defined async function to call per request, with clear
   error behavior if something upstream fails.

## Inputs

- `images: list[str]` (base64) — passed through to
  `VisualAnalysisInput`
- `known_title`, `known_artist`, `known_period`, `medium` — optional,
  passed through to `VisualAnalysisInput`

No `variant_key` input — per "Reuse over re-run," both Curator variants
are always computed; the caller selects which to display after the
fact, not before the pipeline runs.

## Outputs

- `CuratorOutput` for BOTH variants (`curator_output_auction_house`,
  `curator_output_public_gallery`) — the final result, per Curator's
  own spec, computed twice per "Reuse over re-run"
- Additionally, expose the three intermediate agent outputs
  (`VisualAnalysisOutput`, `TitleRiskMatrix`,
  `FinancialValuationResult`) alongside both `CuratorOutput`s in a
  wrapping result object — not just the final narrative. A judge or
  user may want to inspect the actual evidence/reasoning behind the
  final copy (source URLs, risk levels, valuation corridor), not just
  read the finished prose. Discarding the intermediate outputs after
  Curator runs would make the earlier compliance work (source_url
  requirements, evidence_scope, disclosure floor) invisible to anyone
  who isn't reading raw logs.

## Error handling — explicit scope decision

If Visual Art Historian fails, the whole pipeline fails — there's no
meaningful way to run the other three agents without `search_keys`.

**Gate check, before continuing past stage 1:** if
`visual_analysis.is_artwork` is `False`, the pipeline stops
immediately and does not run Provenance/Legal, Financial Valuation, or
Curator — there's no reason to research provenance or estimate a
valuation for a photo that isn't an artwork, and doing so would waste
real API cost (Vertex, Parallel Search) on every affected request. This
raises a typed `NotArtworkError` carrying `is_artwork_reasoning`, so
the caller gets a clear, actionable message rather than a generic
failure or — worse — a confused, low-confidence analysis of a photo of
a sandwich.

If EITHER Provenance/Legal or Financial Valuation fails outright (not
a partial-evidence case — those are already handled internally by each
agent's own retrieval-source resilience — but a total failure of the
agent call itself, e.g. a Vertex outage during the sub-agent calls),
the pipeline fails the whole request rather than attempting a
partial-data Curator run. This is a deliberate scope decision for this
project's timeline, not an oversight: building Curator-level resilience
to partial upstream failure (e.g. "provenance research failed, proceed
without it, disclose the failure instead") is a reasonable future
improvement but adds real complexity for a case that hasn't been
observed as a frequent failure mode in testing so far. Flag back if
this tradeoff should be reconsidered given remaining time before the
deadline.

## Progress reporting

`run_pipeline()` accepts an optional `on_progress: Callable[[str,
str], None] | None` callback — `(stage_key, message)`, not a bare
string. `stage_key` is one of four canonical values matching the four
top-level stages (`"start"`, `"visual_analysis"`,
`"concurrent_research"`, `"curator"`), so the frontend can reliably
GROUP substep messages under their correct parent stage rather than
inferring grouping from message text content, which would be fragile.
`run_pipeline()` builds stage-scoped wrapper closures once per stage
and passes them into `assess_provenance()`, `assess_valuation()`, and
`curate()` — those functions themselves don't need to know about
stage-tagging, they just call whatever callback they're given with
their own message text; `run_pipeline()` is the only place that knows
the stage-key mapping. Both `assess_provenance()` and
`assess_valuation()` get wrappers tagged `"concurrent_research"` (they
share one parent stage in the UI, since they run concurrently as one
visual unit), even though they're two independent calls.

This is not new instrumentation — it's exposing the same
already-logged points introduced in the earlier substep-granularity
change, just with a stage tag added so the frontend can render nested/
indented children under their correct parent rather than a flat list.

`on_progress` failures (e.g. a broken callback) must not affect
pipeline execution — wrap callback invocation so a callback error is
logged but never propagates into the actual agent pipeline.

## Acceptance criteria

- `assess_provenance()` and `assess_valuation()` are verifiably called
  concurrently, not sequentially — total pipeline latency should be
  roughly the max of the two, not the sum (testable by mocking both
  with artificial delays and asserting on wall-clock time, or by
  asserting both are in-flight simultaneously via a mock).
- The full pipeline, called once with a real image, produces a valid
  `CuratorOutput` with no manual intervention between stages — this is
  the acceptance bar for Curator's own task 13, closed out here.
- Given an image where `is_artwork` is `False`, the pipeline raises
  `NotArtworkError` immediately after stage 1 and does NOT call
  Provenance/Legal, Financial Valuation, or Curator — verifiable via
  mocked agent functions asserting the latter three were never
  invoked.
- Intermediate agent outputs are accessible from the pipeline's result,
  not discarded after Curator consumes them.
- Pipeline-level errors (Visual Art Historian failure, or total failure
  of either concurrent agent) propagate as clear, typed errors — not
  swallowed or silently returning partial/malformed output.
- The orchestration function is logged (via `logging_config.py`) at
  each stage transition, so a full pipeline run's timeline is visible
  in logs alone, matching the level of observability each individual
  agent already has.
- Given an `on_progress` callback, `run_pipeline()` invokes it with
  `(stage_key, message)` at each substep completion point — verifiable
  by a mocked callback asserting both the stage_key values are always
  one of the four canonical keys, and message content/order matches
  the real execution sequence.
- Substeps belonging to `assess_provenance()` and `assess_valuation()`
  are both tagged `"concurrent_research"`, even though they're
  reported by two independently-running functions — this lets the
  frontend group both agents' substeps under one shared parent stage.
- A raising `on_progress` callback does not crash or interrupt the
  pipeline — the error is caught and logged, execution continues.

## Out of scope

- No HTTP/FastAPI concerns — that's a separate, later spec.
- No partial-failure resilience at the pipeline level beyond what's
  already built into each individual agent's retrieval layer (see
  "Error handling" above).