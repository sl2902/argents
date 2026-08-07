# Requirements: Financial Valuation Agent

## Purpose

Given `search_keys` from Visual Art Historian, produce a heuristic
valuation (low/high estimate) for the artwork, derived from
public comparable sales — not a definitive appraisal, and explicitly
labeled as such throughout.

This agent runs after Provenance/Legal in the pipeline (or concurrently
with it, if `pipeline.py`'s design allows — see design.md) and its
output feeds Curator's final synthesis alongside Visual Art Historian's
and Provenance/Legal's.

## Architecture (see also `.kiro/steering/structure.md`)

Same retrieval-then-dual-reasoning pattern as Provenance/Legal:

1. **Retrieval (shared, single pass):** query Parallel Search for
   public auction press coverage and Wikidata sale-price properties
   (P2296/P1088) — once, producing one evidence bundle consumed by both
   sub-agents below.
2. **Dual reasoning (concurrent):** Conservative Appraiser (floor) and
   Bullish Specialist (ceiling), per `config/agents.yaml`, each reason
   over the SAME retrieved evidence bundle and produce independent
   estimates, run concurrently via `asyncio.gather`, then synthesized
   into a single valuation corridor.

## Evidence scope — same lesson as Provenance/Legal, applied from the start

**This is carried over directly from a real bug found and
fixed in Provenance/Legal.** When `search_keys.work_title` is `None` (the common case for
blind-discovery input), a comparable-sales search by artist name alone
returns sale records for MANY DISTINCT works by that artist, not
comps specifically matched to this piece. Left unscoped, this risks the
exact failure observed in Provenance/Legal testing: sub-agents reasoning
as if a scattered set of unrelated sale prices described "this artwork's
market value" rather than "this artist's general market range."

Requirements, directly mirroring the Provenance/Legal fix:
- Every comparable sale in the evidence bundle carries a
  `source_entity_id` where one exists (a Wikidata QID for the specific
  sold work, if identifiable) — `None` where a comp comes from a news
  article with no single identifiable work.
- `evidence_scope: "specific_object" | "artist_general"` is set the
  same way: `"specific_object"` only when `work_title` is known and
  confidently matched; otherwise `"artist_general"`.
- In `"artist_general"` mode, both sub-agents MUST frame their
  valuation as "this artist's general market range" language, not "this
  artwork is worth X" — and must not present a scattered set of
  different works' sale prices as if they were comps specifically
  representative of the piece being valued.

## User stories

1. As a gallery researcher, I get a low/high valuation signal backed
   by real, cited comparable sales — not a single confident number that
   overstates certainty real auction houses themselves don't claim.

2. As a buyer weighing risk, I want the Conservative Appraiser's floor
   estimate: illiquidity discounts, hammer prices net of buyer's
   premium, current market headwinds for this artist/period.

3. As a buyer assessing upside, I want the Bullish Specialist's ceiling
   estimate: private-treaty/replacement value, artist momentum,
   scarcity premium, exhibition history.

4. As the Curator agent (downstream consumer), I receive a synthesized
   valuation corridor and its evidentiary basis, so exhibition copy
   doesn't overstate or understate the piece's likely market value.

## Inputs

- `search_keys: ProvenanceSearchKeys` (from Visual Art Historian):
  `work_title`, `primary_artist_attribution`, `probable_creation_window`,
  `style_and_movement`, `search_keywords`
- Optional: `TitleRiskMatrix` from Provenance/Legal, if available —
  documented provenance red flags can legitimately affect valuation
  (e.g. an unresolved title dispute reduces marketability), so the
  Conservative Appraiser in particular should be able to factor this in
  if provided. Not a hard dependency — this agent must still function
  if Provenance/Legal's output isn't passed in.

## Outputs (structured, Pydantic-validated)

**Evidence bundle:**
- `comparable_sales`: list of `{description: str, price_usd: float |
  None, sale_date: str | None, source_url: str, source_entity_id: str |
  None, source_type: "wikidata" | "parallel_search"}` — `price_usd` may
  be `None` if a source discusses a sale without giving a clear figure;
  don't fabricate a number to fill the field.
- `evidence_scope`: same two-value enum as Provenance/Legal

**Conservative Appraiser sub-output:**
- `floor_estimate_usd`: float
- `methodology`: string — states which comps were used and why, and
  explicitly names the discounts applied (illiquidity, buyer's premium,
  market headwinds)
- `confidence`: "low" | "moderate" | "high" — reflects how directly the
  available comps actually match this artist/period/medium, not just
  how confidently the sub-agent writes

**Bullish Specialist sub-output:**
- `ceiling_estimate_usd`: float
- `methodology`: string — states which comps were used, artist momentum
  factors, scarcity/exhibition-history reasoning
- `confidence`: "low" | "moderate" | "high"

**Synthesized output (what Curator consumes):**
- `valuation_corridor`: `{low_estimate_usd: float, high_estimate_usd:
  float}`
- `corridor_summary`: string — states the range and, same as
  Provenance/Legal's `synthesis_summary`, does not silently smooth over
  a case where the two estimates are wildly divergent (e.g. if floor
  and ceiling differ by more than some notable margin, that gap itself
  is worth naming, not just presenting two numbers side by side as if
  they were expected to be close)
- `requires_human_review`: bool — true when comps are sparse/weak
  (`evidence_scope: "artist_general"` AND fewer than some minimum
  number of comps), or when both sub-agents' `confidence` is "low"

## Acceptance criteria

- Every `comparable_sales` entry with a stated price carries a real,
  working `source_url` — no fabricated price attached to a claim.
- `price_usd` is `None` rather than a guessed number when a source
  doesn't give a clear figure.
- Retrieval happens exactly once per request; both sub-agents reason
  over the identical evidence bundle.
- The two sub-agents run concurrently (`asyncio.gather`), not
  sequentially.
- Given `work_title = None` and a prolific/well-known artist, both
  sub-agents' `methodology` text explicitly frames the estimate as
  general market range for the artist, not a specific-object valuation
  — mirroring the exact language pattern validated in Provenance/Legal
  testing (e.g. "these comps represent the artist's market broadly, not
  necessarily this specific piece").
- `valuation_corridor` is never presented as a single point estimate —
  `low_estimate_usd` and `high_estimate_usd` are always both populated,
  even when the two sub-agents' figures are close.
- Parallel Search query construction follows the same hardening already
  built for Provenance/Legal: filter empty/placeholder search terms,
  skip the call if no usable anchor remains, and apply a relevance
  filter on results before adding them to `comparable_sales`.
- Wikidata queries use a client-level default `LIMIT` (already built
  into `WikidataClient` for Provenance/Legal — reuse it, don't
  reimplement).
- Core retrieval logic and both sub-agent reasoning paths are covered
  by unit tests with mocked clients — not exercised only manually.
- Core parsing/validation logic and the evidence-scoping logic are
  covered by unit tests with a mocked model/client — not exercised only
  manually.
- The agent logs (via `logging_config.py`, not `print()`): retrieval
  call latency/failures per source, which estimates each sub-agent
  produced, and whenever `requires_human_review` is set to true.
- Agent voice/domain framing and model parameters are loaded from
  `config/agents.yaml` via `config_loader.get_dual_agent_config(
  "financial_valuation")` — not hardcoded in the agent module.

## Out of scope

- This is not a certified appraisal and must never be presented as one
  — the README and any UI copy must state valuations are heuristic
  estimates from public comps.
- Does not attempt to access paywalled auction databases (Artnet,
  MutualArt, Sotheby's/Christie's ledgers) — public comps only, per the
  earlier scoping decision.