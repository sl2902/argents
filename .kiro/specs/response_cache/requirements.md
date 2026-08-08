# Requirements: Response Cache

## Purpose

Avoid re-running the full pipeline (6+ Vertex calls, 60-90+ seconds,
real API cost) for an identical request — same image bytes and same
optional metadata — by caching the completed `AnalyzeResponse` to
local disk, keyed by a hash of the actual input.

## Explicit scope decision

This is a local filesystem cache, not a persistent external store. On
Cloud Run (or any serverless/container deployment target), local disk
is ephemeral — it does not survive a restart, redeploy, or a request
landing on a different instance. This cache is useful WITHIN a single
running process (repeat requests during testing/demo rehearsal won't
re-burn Vertex calls) but should not be relied on to persist across
restarts or scale across multiple instances. A production version
would need external persistent storage (e.g. a GCS bucket, a small
database). This mirrors the same explicit scope-decision treatment
already given to the in-memory `JOBS` store.

## Requirements

- Cache key is computed from the raw image bytes AND the optional
  metadata fields (`known_title`, `known_artist`, `known_period`,
  `medium`) — different metadata can genuinely change the analysis
  (e.g. `known_title` changes `evidence_scope` in Provenance/Legal and
  Financial Valuation), so it must be part of the key, not just the
  image.
- On a cache hit, the request still goes through the normal
  job-polling flow — `POST /api/analyze` still returns a `job_id`, and
  `GET /api/status/{job_id}` is still how the result is retrieved —
  just pre-populated as already `complete`, with no pipeline execution
  triggered. This keeps the frontend's polling logic uniform with no
  special-casing for cache hits vs. misses.
- On a cache miss, the pipeline runs normally, and the result is
  written to the cache after successful completion — a failed run is
  never cached (don't cache errors).
- Cache reads/writes must not affect the actual analysis in any way —
  this is purely an optimization layer around calling `run_pipeline()`,
  not a change to what it computes.

## Acceptance criteria

- Given two requests with identical image bytes and identical metadata,
  the second request's job completes near-instantly (no real pipeline
  execution, verifiable via mocked `run_pipeline()` never being called
  on the second request) and returns the same result as the first.
- Given two requests with identical image bytes but DIFFERENT
  `known_title`, both are treated as cache misses (different keys) —
  verifiable the same way.
- A failed pipeline run does not get cached — a subsequent identical
  request still attempts a real run, not a cached failure.
- Cache key computation and hit/miss logic are covered by unit tests
  with a mocked filesystem/temp directory — not exercised only
  manually.