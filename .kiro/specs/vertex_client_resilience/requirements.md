 # Requirements: Vertex Client Resilience (transient error retry/backoff)

## Purpose

Harden the shared `clients/vertex.py` against transient failures
observed in real testing:
- `429 RESOURCE_EXHAUSTED`, when concurrent Vertex calls (stage 2's
  two sub-agents; stage 3's two Curator calls) burst against Vertex's
  per-minute rate quota.
- Server-disconnect errors ("Server disconnected without sending a
  response"), observed after a ~60.3s call — suspiciously close to a
  common default timeout value, worth investigating as a possible
  self-inflicted timeout before treating purely as a retry problem
  (see requirements below).

A single transient failure of either kind currently fails the entire
pipeline run — a real demo-day risk given how many concurrent, and how
long individual, calls this architecture makes by design.

## Requirements

- **First, check for a self-inflicted timeout.** Before implementing
  retry logic for the disconnect case, check whether the Vertex client
  has an explicit request timeout configured at or near 60 seconds. A
  disconnect at ~60.3s is suspicious — that's a common default
  timeout for HTTP clients/proxies. Sub-agent calls with heavy prompts
  have legitimately taken 40-43s+ in testing, so a 60s ceiling leaves
  little margin under concurrent load. If an explicit near-60s timeout
  is found, increase it (e.g. to 120s) as the primary fix for this
  specific error. If no such timeout is configured, treat this as a
  genuine transient network issue and rely on the retry logic below.
- The Vertex client retries on BOTH `429 RESOURCE_EXHAUSTED`
  (detectable from the error's status/code) AND server-disconnect/
  connection-level errors, with exponential backoff — starting delay
  ~2s, doubling per retry, capped at a reasonable max (e.g. 3 retries
  total, ~2s/4s/8s), tuned so total added latency stays bounded rather
  than compounding pipeline runs that are already 60-90+ seconds.
- Other error types (auth failures, malformed requests, genuine model
  errors) do NOT get this retry treatment — they should fail fast,
  same as before. Retrying a malformed request repeatedly wastes time
  and doesn't fix anything.
- Each retry attempt is logged at WARNING (not ERROR, since a
  successful retry means the overall call succeeded) with the attempt
  number, delay, and which error type triggered the retry — so a
  demo-day hit is visible in logs even if the end user never sees it,
  because the retry succeeded transparently.
- If all retries are exhausted, the original error propagates as
  before — this is a mitigation for transient bursts/blips, not a
  guarantee against sustained quota exhaustion or a genuine extended
  outage.

## Acceptance criteria

- Given a mocked Vertex call that returns 429 twice then succeeds on
  the third attempt, the client retries automatically and returns the
  successful result — the caller never sees the 429.
- Given a mocked Vertex call that raises a disconnect/connection error
  twice then succeeds, the client retries automatically — same
  behavior as the 429 case.
- Given a mocked Vertex call that returns a non-retryable error (e.g.
  400, auth failure), the client does NOT retry — it fails
  immediately, same as current behavior.
- Given a mocked Vertex call that fails on every attempt up to the
  retry limit (either error type), the client exhausts retries and
  propagates the original error — does not retry indefinitely.
- If a near-60s explicit timeout was found and increased, this is
  documented in code comments explaining why the value was chosen
  (e.g. "increased from 60s; sub-agent calls have taken up to 43s+
  under normal conditions, leaving insufficient margin at 60s").
- Retry attempts are covered by unit tests with a mocked client — not
  exercised only against the real API (these errors are hard to
  reliably reproduce against a live service on demand).