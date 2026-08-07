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
              curate()  [Curator]
```

`assess_provenance()` and `assess_valuation()` both depend only on
Visual Art Historian's `search_keys` output, not on each other — they
must run concurrently via `asyncio.gather`, not sequentially, since
there's no data dependency between them and sequential execution would
roughly double end-to-end latency for no benefit (each individual call
already takes 15-40+ seconds based on testing).

`curate()` runs last and requires the outputs of all three prior
stages.

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
- `variant_key: str | None` — passed through to `CuratorInput` for
  Curator's voice selection

## Outputs

- `CuratorOutput` — the final result, per Curator's own spec
- Additionally, expose the three intermediate agent outputs
  (`VisualAnalysisOutput`, `TitleRiskMatrix`,
  `FinancialValuationResult`) alongside the final `CuratorOutput` in a
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
- Core orchestration logic (ordering, concurrency, error propagation)
  is covered by unit tests with mocked agent functions — not exercised
  only manually against real APIs.

## Out of scope

- No HTTP/FastAPI concerns — that's a separate, later spec.
- No partial-failure resilience at the pipeline level beyond what's
  already built into each individual agent's retrieval layer (see
  "Error handling" above).