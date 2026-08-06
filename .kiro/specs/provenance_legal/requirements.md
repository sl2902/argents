# Requirements: Provenance & Legal Agent

## Purpose

Given the `search_keys` produced by the Visual Art Historian agent,
research the artwork's ownership history and check for documented
red flags (theft, plunder, undocumented gaps in known high-risk
windows), producing a structured title risk matrix that a gallery or
auction house can act on before an exhibition or sale.

This agent runs SECOND in the pipeline, after Visual Art Historian and
before Curator — it consumes `search_keys` as input and its output
feeds Curator's final synthesis.

## Architecture (see also `.kiro/steering/structure.md`)

This agent is not a single reasoning step. It has two stages:

1. **Retrieval (shared, single pass):** query Wikidata SPARQL, Met/AIC
   raw provenance text fields, and Parallel Search for public theft/
   plunder records and press coverage — once, producing one evidence
   bundle consumed by both sub-agents below.
2. **Dual reasoning (concurrent):** two sub-agents — Compliance Auditor
   (skeptic) and Provenance Historian (advocate) — each reason over the
   SAME retrieved evidence bundle and produce independent risk
   assessments, run concurrently via `asyncio.gather`, then synthesized
   into a single title risk matrix.

## User stories

1. As a gallery researcher, I get a structured provenance timeline for
   a work, built from real, cited public sources, not a single opaque
   "clear" or "flagged" verdict — so I can see the actual evidence
   behind the risk assessment.

2. As a compliance-minded buyer, I want the Compliance Auditor's
   skeptical read: does this work have an unexplained gap in a known
   high-risk window (WWII-era 1933-1945, pre-1970 UNESCO export)? I
   want that flagged even if it might be explainable, not silently
   smoothed over.

3. As a researcher who doesn't want every historical gap treated as
   disqualifying, I want the Provenance Historian's contextualizing
   read: is this gap consistent with ordinary historical
   record-keeping norms (e.g. undocumented family inheritance), or is
   it genuinely unusual?

4. As the Curator agent (downstream consumer), I receive a synthesized
   title risk matrix and the underlying evidence, so I can write
   accurate exhibition copy that doesn't overstate or understate
   provenance certainty.

## Inputs

- `search_keys: ProvenanceSearchKeys` (from Visual Art Historian):
  `primary_artist_attribution`, `probable_creation_window`,
  `style_and_movement`, `detected_signatures_or_marks`,
  `search_keywords`
- Optional: any known metadata passed through from the original user
  input (title, claimed provenance notes, if the user has them)

## Outputs (structured, Pydantic-validated)

**Evidence bundle (internal, also exposed for transparency):**
- `retrieved_facts`: list of `{claim: str, source_url: str,
  source_type: "wikidata" | "met" | "aic" | "parallel_search"}`

**Compliance Auditor sub-output:**
- `identified_gaps`: list of ownership-history gaps, each with the
  approximate window and whether it falls in a known high-risk period
- `risk_level`: "low" | "moderate" | "red_flag"
- `reasoning`: string explaining the skeptical read

**Provenance Historian sub-output:**
- `contextual_notes`: string — historical context for any identified
  gaps (does NOT dismiss red flags, only contextualizes them)
- `supporting_evidence`: list of retrieved facts supporting
  uninterrupted or well-documented ownership, if any exist
- `risk_level`: "low" | "moderate" | "red_flag" (independently assessed
  — may differ from Compliance Auditor's)

**Synthesized output (what Curator actually consumes):**
- `title_risk_matrix`: combines both sub-agent assessments; does not
  average them into a single number — presents both readings plus a
  synthesized summary
- `requires_human_review`: bool — true whenever the two sub-agents
  disagree on `risk_level`, or either flags "red_flag"

## Acceptance criteria

- Every claim in `retrieved_facts` carries a real, working `source_url`
  — no claim is asserted without one.
- Retrieval happens exactly once per request; both sub-agents reason
  over the identical evidence bundle (verifiable: same
  `retrieved_facts` list passed to both).
- The two sub-agents run concurrently (`asyncio.gather`), not
  sequentially.
- Given an artwork with a real, well-documented gap in the 1933-1945
  window (test case, e.g. a work with public Wikidata plunder-related
  properties), Compliance Auditor flags `risk_level: "red_flag"` and
  Provenance Historian's `risk_level` may differ — the synthesis must
  surface disagreement rather than silently picking one.
- Given an artwork with no gaps and clean, well-documented ownership
  history, both sub-agents converge on `risk_level: "low"` and
  `requires_human_review` is false.
- Neither sub-agent asserts a theft/plunder flag without a citable
  `source_url` in `retrieved_facts` backing it.
- Core retrieval logic and both sub-agent reasoning paths are covered
  by unit tests with mocked clients (Wikidata, Met/AIC, Parallel
  Search) — not exercised only manually.
- The agent logs (via `logging_config.py`, not `print()`): retrieval
  call latency/failures per source, which sub-agent risk levels were
  produced, and whenever `requires_human_review` is set to true.

## Out of scope

- This is not a legal authority on stolen-art status — it surfaces
  documented, publicly retrievable red flags. It does not replace a
  formal Art Loss Register / Interpol check (both are paywalled/
  access-restricted and out of scope for this project).
- Does not attempt full chain-of-title reconstruction back to the
  work's creation — works with what's retrievable from the sources
  listed above.