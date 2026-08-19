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
  `known_period`, `medium`). Starts the pipeline as a background task
  and returns immediately with `{"job_id": "..."}` — does NOT block
  until the pipeline completes. No `variant_key` form field — per the
  pipeline's "Reuse over re-run" design, BOTH Curator variants
  (auction_house, public_gallery) are always computed and returned in
  one response; the caller/frontend selects which to display without
  a second request.
- `GET /api/status/{job_id}` — polled by the frontend to get real
  progress. Returns the job's current status (`queued` | `running` |
  `complete` | `failed`), a list of progress log messages (populated
  via `run_pipeline()`'s `on_progress` callback as real stages
  complete — not a heuristic timer), and once `complete`, the full
  `AnalyzeResponse` result. On `failed`, includes an error message and
  the failing stage, same information the previous synchronous error
  handling provided.
- `GET /api/health` — trivial liveness check; returns 200 with basic
  status. No agent logic invoked. Useful for judges/deployment checks
  without burning API quota.

## Job store — explicit scope decision

Job state is held in an in-memory dictionary within the API process
(`job_id -> {status, logs, result | error}`). This is a deliberate,
acknowledged scoping decision for this project's timeline, not an
oversight:

- **Single-instance only.** If the deployment ever runs multiple
  backend instances (e.g. Cloud Run autoscaling beyond one instance), a
  status poll could hit a different instance than the one running the
  job and get a false "not found." For a single-instance hackathon
  demo/judging deployment this is acceptable; it would need a real
  shared store (Redis, a database) to be production-safe. Document
  this limitation directly in the README, not just here.
- **No persistence across restarts** — a job in progress during a
  server restart is lost. Acceptable for this project's scope.
- Flag back if remaining time before the deadline makes it worth
  revisiting this tradeoff (e.g. if deployment ends up needing multiple
  instances for some other reason).

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
- **Curator output — both variants**: `exhibition_narrative`,
  `wall_label`, `suggested_title`, `disclosures` for BOTH
  `auction_house` and `public_gallery`, so the frontend can toggle
  between them client-side with zero additional requests.
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

Since the pipeline now runs as a background task, errors surface via
job status (`status: "failed"`), not a synchronous HTTP error response
from `/api/analyze` itself (that endpoint only fails synchronously for
request-shape problems — e.g. no file uploaded at all — before the
background task even starts).

- Malformed upload request itself (no file, wrong content type) → 400
  from `POST /api/analyze` directly, before any job is created.
- Once a job is running: `NotArtworkError`, or any other typed agent
  exception, results in `GET /api/status/{job_id}` returning
  `status: "failed"` with an error message and the failing stage
  identified — not a 500 from the status endpoint itself (the status
  endpoint succeeds at reporting that the job failed; the job's
  content is what failed).
- Do not swallow errors to always report `status: "complete"` — per
  the pipeline's own documented scope decision (total stage failure
  fails the whole request), the job status should reflect that
  honestly.

## Acceptance criteria

- `POST /api/analyze` returns a `job_id` immediately (does not block
  for 60-90+ seconds) and `GET /api/status/{job_id}` reflects real
  pipeline progress — verifiable by polling during a real run and
  confirming `logs` grows with real stage-completion messages, not a
  fixed/predetermined sequence unrelated to actual execution timing.
- Response includes both sub-agents' full reasoning for both dual-agent
  stages, not just synthesized summaries — verifiable by checking the
  final `AnalyzeResponse` (delivered via `GET /api/status/{job_id}`
  once complete) directly exposes `compliance_auditor`/
  `provenance_historian` and `conservative_appraiser`/
  `bullish_specialist` as distinct objects.
- Response exposes `provenance_evidence_scope` and
  `valuation_evidence_scope` (each `"specific_object"` or
  `"artist_general"`) — a consumer needs this to correctly frame
  whether retrieved evidence is about the specific artwork being
  assessed or the artist's body of work in general; without it, a
  serious historical reference (e.g. documented plunder history) could
  be misread as a claim about the tested piece itself when it isn't.
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