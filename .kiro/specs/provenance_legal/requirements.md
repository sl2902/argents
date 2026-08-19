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
- `cited_evidence`: list of every retrieved fact this sub-agent's
  reasoning actually relies on or references in `contextual_notes` —
  in EITHER direction. This is NOT limited to facts supporting clean/
  uninterrupted ownership; if the Historian's reasoning discusses a
  risk-relevant fact (e.g. a documented wartime-era owner), that fact
  must appear here too. A field that only captured exculpatory
  evidence would create a mismatch between what's cited in prose and
  what's listed as evidence — this field is symmetric with what
  `contextual_notes` actually references, not a one-directional
  "evidence for a clean narrative" list.
- `risk_level`: "low" | "moderate" | "red_flag" (independently assessed
  — may differ from Compliance Auditor's)

**Synthesized output (what Curator actually consumes):**
- `title_risk_matrix`: combines both sub-agent assessments; does not
  average them into a single number — presents both readings plus a
  synthesized summary
- `requires_human_review`: bool — true whenever the two sub-agents
  disagree on `risk_level`, or either flags "red_flag"

## Real-world grounding: when the standard test can't be applied

Museum practice (per AAM/AAMD Nazi-era provenance guidelines, in place
since 1998-99) doesn't assess risk by how alarming general historical
context feels. It uses a mechanical, OBJECT-SPECIFIC test: was this
specific object created before 1946, acquired by the current holder
after 1932, did it change hands 1933-1945, and was it plausibly in
continental Europe during that window? If a work meets that test, it's
a "covered object" requiring active research and disclosure - full
stop, regardless of how normal provenance gaps are for old art in
general. If a work CANNOT be evaluated against that test - which is
exactly the `evidence_scope: "artist_general"` case, where there's no
way to know if this specific piece was even in Europe in 1933-1945 -
the honest, professionally-grounded answer isn't "probably fine" or
"moderate risk." It's that the standard test cannot be applied without
object-specific data, and the same AAM/AAMD-style guidelines would
recommend active research before the question can be answered at all.

Forcing every case into `low`/`moderate`/`red_flag` was itself
dishonest in `artist_general` mode - it implied a risk judgment was
being made when the real, correct answer is that no judgment can be
made yet. `risk_level` gains a fourth value:
`"cannot_determine_insufficient_object_data"`.

- Used ONLY in `evidence_scope: "artist_general"` mode, when the
  retrieved evidence describes the artist's body of work in general
  and cannot be tied to the specific object being assessed.
- Both sub-agents may independently reach this state - it isn't
  something only one persona can express. A sub-agent should use it
  instead of a forced `low`/`moderate`/`red_flag` guess whenever it
  genuinely cannot ground a risk judgment in object-specific evidence.
- When either sub-agent reaches this state, `requires_human_review`
  is automatically `true` in synthesis - "we can't determine this
  without more information" is inherently review-worthy, not a
  clean "low risk" result.
- `reasoning`/`contextual_notes` must explicitly say so in plain
  language - e.g. "Standard object-specific provenance review (per
  museum due-diligence practice) requires knowing whether this
  specific piece changed hands during 1933-1945 and was in continental
  Europe at the time. That information isn't available from a
  general artist-level search. Object-specific research is needed
  before this question can be answered."

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
- Given a request with no known `work_title` and an artist with many
  documented works (e.g. Claude Monet), `evidence_scope` is set to
  `"artist_general"`, and neither sub-agent's reasoning treats facts
  from different `source_entity_id` values as describing one
  continuous object history — each sub-agent's output explicitly
  frames its assessment as general artist-level risk context, not a
  specific-object finding, when in this mode.
- Given a request with a known `work_title` that matches a single
  Wikidata/AIC entity, `evidence_scope` is `"specific_object"` and
  facts sharing that entity's `source_entity_id` may be reasoned over
  as one object's ownership history.
- A `red_flag` risk_level in `"artist_general"` mode is only used when
  there is truly no way to express appropriate uncertainty otherwise
  (e.g. every documented work by this artist has a plunder history) —
  the default for genuinely unmatched artist-general evidence, where
  neither sub-agent can ground a judgment in object-specific data, is
  `"cannot_determine_insufficient_object_data"`, not a confident
  `red_flag` OR a falsely-comfortable `moderate`/`low` phrased as if
  it's a specific-object finding. `moderate`/`low`/`red_flag` remain
  available in `artist_general` mode only when the sub-agent has a
  genuine, stated basis for that judgment even without object-specific
  data (e.g. every single retrieved work by the artist shares the same
  clean or same alarming pattern) — the new state is for the common
  case where the evidence is simply too disconnected from the specific
  object to support any risk judgment at all.
- Neither sub-agent asserts a theft/plunder flag without a citable
  `source_url` in `retrieved_facts` backing it.
- Any fact dropped during retrieval due to a malformed/invalid
  `source_url` (or other validation failure) increments
  `EvidenceBundle.rejected_fact_count` and is logged at WARNING — data
  loss during retrieval is visible in the output itself, not only in
  logs.
- Core retrieval logic and both sub-agent reasoning paths are covered
  by unit tests with mocked clients (Wikidata, Met/AIC, Parallel
  Search) — not exercised only manually.
- The agent logs (via `logging_config.py`, not `print()`): retrieval
  call latency/failures per source, which sub-agent risk levels were
  produced, and whenever `requires_human_review` is set to true.
- Parallel Search query construction is robust against sparse input:
  empty or placeholder strings in `search_keywords` are filtered out
  before building a query, and if too little identifying information
  remains (e.g. no usable title/artist term at all) the agent skips the
  Parallel Search call for that request rather than searching on bare
  generic terms like "Nazi plunder" alone — a query with no
  artwork-specific anchor produces irrelevant results, which is worse
  than no results.
- Parallel Search results are filtered for basic relevance before being
  added to `retrieved_facts` — a result sharing no keyword overlap with
  the artwork's identifying terms (title, artist, or search keywords)
  is dropped rather than included as if it were evidence about this
  specific work.

## Out of scope

- This is not a legal authority on stolen-art status — it surfaces
  documented, publicly retrievable red flags. It does not replace a
  formal Art Loss Register / Interpol check (both are paywalled/
  access-restricted and out of scope for this project).
- Does not attempt full chain-of-title reconstruction back to the
  work's creation — works with what's retrievable from the sources
  listed above.