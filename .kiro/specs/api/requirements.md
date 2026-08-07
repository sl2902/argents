# Requirements: API Layer

## Purpose

Expose `run_pipeline()` over HTTP via FastAPI, with a response shape
specifically designed to showcase the multi-agent architecture — not
just the final curated result, but the visible dual-agent reasoning
(Compliance Auditor vs. Provenance Historian; Conservative Appraiser
vs. Bullish Specialist) and the evidence trail behind it. This is the
layer the frontend calls; it has no agent logic of its own.

## User stories

1. As someone watching a demo of this app, I can see that two
   different sub-agents assessed provenance risk and may have
   disagreed — not just a single opaque "risk: moderate" output — so
   the multi-agent architecture is visible, not hidden behind a
   summary.

2. As someone watching a demo, I can see how long each stage took and
   that Provenance/Legal and Financial Valuation ran concurrently — the
   parallelism is a real architectural choice worth surfacing, not an
   invisible implementation detail.

3. As a frontend developer, I get one clear endpoint to call with an
   image, and a response shape I can map directly to UI cards per
   agent, without needing to understand the internal Pydantic model
   nesting from `pipeline.py` myself.

## Endpoints

- `POST /api/analyze` — accepts a multipart image upload (one or more
  files) plus optional form fields (`known_title`, `known_artist`,
  `known_period`, `medium`, `variant_key`). Converts uploaded images to
  base64 internally, calls `run_pipeline()`, returns the shaped
  response described below.
- `GET /api/health` — trivial liveness check; returns 200 with basic
  status. No agent logic invoked. Useful for judges/deployment checks
  without burning API quota.

## Response shape — showcase-oriented, not a raw passthrough

The response must include:

- **Visual analysis**: attribution (with hedge language intact),
  period/style, composition/condition/authenticity notes
- **Provenance — both sub-agent views, not just the synthesis**:
  Compliance Auditor's `identified_gaps`/`risk_level`/`reasoning` AND
  Provenance Historian's `contextual_notes`/`risk_level`/
  `cited_evidence`, plus the synthesized `synthesis_summary` and
  `requires_human_review`. Showing only the synthesized result would
  hide the actual multi-agent behavior this project is built to
  demonstrate.
- **Valuation — both sub-agent views**: Conservative Appraiser's
  `floor_estimate_usd`/`primary_comp`/`methodology`/`confidence` AND
  Bullish Specialist's equivalent fields, plus `valuation_corridor` and
  `corridor_summary`.
- **Curator output**: `exhibition_narrative`, `wall_label`,
  `suggested_title`, `disclosures`, `variant_used`.
- **Evidence trail**: a representative sample of `retrieved_facts` /
  `comparable_sales` with their `source_url`s — enough to demonstrate
  real, citable sources are behind the findings, without necessarily
  dumping all 40-56 entries verbatim (see "Response size shaping"
  below).
- **Stage timings**: per-stage duration in ms, and an explicit
  indicator that Provenance/Legal and Financial Valuation ran
  concurrently (e.g. a shared "stage 2 wall-clock duration" alongside
  each individual agent's own duration, so a UI can visually
  demonstrate the parallelism rather than just listing four sequential
  numbers).

## Response size shaping — API-layer concern only

Some `retrieved_facts`/`comparable_sales` entries contain long raw
scraped page text (observed: 1000+ characters from Parallel Search
results). For the API response specifically (NOT a change to internal
agent behavior or their own data structures):
- Truncate each evidence entry's `description`/`claim` text to a
  reasonable length (e.g. ~300 characters) for display purposes, with
  the full `source_url` always preserved so a user can click through
  for the complete source.
- This is response-shaping in the API layer only — it must not modify
  or truncate what the agents themselves compute, store, or use in
  their own reasoning. `PipelineResult` internally stays exactly as
  the agents produced it; only the HTTP response is shaped for
  display.

## Error handling

- Image upload validation errors (no file, wrong type, `InvalidImageError`
  from Visual Art Historian) -> 400 with a clear message.
- Pipeline stage failures (typed errors from any agent) -> 500 with a
  message identifying which stage failed, not a bare stack trace.
- Do not swallow errors to always return 200 — per the pipeline's own
  documented scope decision (total stage failure fails the whole
  request), the API should reflect that honestly with an appropriate
  error status, not silently degrade.

## Acceptance criteria

- `POST /api/analyze` response includes both sub-agents' full
  reasoning for both dual-agent stages, not just synthesized summaries
  — verifiable by checking the response schema directly exposes
  `compliance_auditor`/`provenance_historian` and
  `conservative_appraiser`/`bullish_specialist` as distinct objects.
- Response includes per-stage timing with concurrency visible (stage 2
  duration is NOT simply the sum of both agents' individual
  durations).
- Evidence entries in the response have truncated display text but
  intact, complete `source_url`s.
- `GET /api/health` responds without invoking any agent/model call.
- Error responses use appropriate HTTP status codes and identify which
  stage failed, not just a generic 500.
- CORS is configured to allow the frontend's origin (exact origin TBD
  once frontend hosting is decided — use a permissive dev default for
  now, tighten before submission if time allows).
- Core response-shaping logic (truncation, timing aggregation, error
  mapping) is covered by unit tests — not exercised only manually.

## Out of scope

- No authentication/rate limiting — single-user hackathon demo scope.
- No streaming/WebSocket progress updates — the endpoint is a single
  blocking request/response; the frontend can still show a loading
  state, it just won't get live per-stage updates mid-request. Worth
  reconsidering only if there's spare time before the deadline.