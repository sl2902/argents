# Design: Provenance & Legal Agent

## Evidence scope — preventing cross-object contamination

**This is the central correctness concern for this agent.** When
`search_keys.work_title` is `None` (no specific title known — the
common case for blind-discovery input), Wikidata and AIC queries can
only search by artist name, which returns facts about MULTIPLE
DISTINCT works by that artist, not one object's provenance. Left
ungrouped, these get reasoned over as if they described a single
continuous ownership chain — this was observed in testing: a Wikidata
entity's real Hermann Göring ownership record and an unrelated 2024 FBI
restitution news story about a *different* Monet pastel were merged by
the sub-agents into one fabricated narrative about "the artwork."

**Fix, two parts:**

1. `RetrievedFact` gains a `source_entity_id: str | None` field —
   the Wikidata QID, AIC object ID, or equivalent stable identifier
   the fact came from, where available. Facts from a search result
   or general web page with no single identifiable object (most
   Parallel Search hits) get `None`.
2. `EvidenceBundle` gains `evidence_scope: Literal["specific_object",
   "artist_general"]`, set based on whether `work_title` was
   available AND a Wikidata/AIC query successfully matched to a
   single entity:
   - `"specific_object"`: a title was known and matched to one
     entity — facts sharing that `source_entity_id` can be reasoned
     over as one object's history.
   - `"artist_general"`: no title, or no confident single-entity
     match — facts may span multiple works by the artist. Both
     sub-agents MUST be explicitly told this in their prompt and
     MUST NOT synthesize a single-object ownership narrative from
     facts with different `source_entity_id` values. Any claim in
     `reasoning`/`contextual_notes` must be scoped to "general risk
     context for this artist" language, not "the artwork's history."

`risk_level` in `"artist_general"` mode should reflect genuine
inability to verify the specific object — e.g. "moderate" framed as
"cannot confirm this specific piece's history; artist has documented
looting-era risk in general" — not a confident "red_flag" phrased as
if it's a finding about the specific artwork, unless there is truly no
alternative (see acceptance criteria in requirements.md).

**Query bounding:** `WikidataClient` must apply a default `LIMIT` to
any query that doesn't explicitly specify one — not just the
artist-driven query in this agent. Without one, a prolific artist (e.g.
Claude Monet, with hundreds of documented works) produces a query
returning triples across potentially hundreds of distinct entities,
which is slow and prone to timing out — observed in testing: a
30-second timeout on an unbounded artist-only query. A client-level
default (rather than hardcoding a LIMIT into this one query string)
protects any future caller of `WikidataClient` that queries without
explicitly bounding results, not just this agent's current query
shape. This is also consistent with `evidence_scope: "artist_general"`
mode's own definition — since that mode already treats results as
general risk context rather than a complete/authoritative record for
one object, a bounded, representative sample is correctness-
appropriate, not a compromise. A reasonable starting default is 50,
overridable per-call where a caller has a specific reason to set a
different bound.

## Architecture

```
ProvenanceSearchKeys (from Visual Art Historian)
        │
        ▼
┌────────────────────────────────────┐
│ retrieval.py                        │
│  - Wikidata SPARQL query            │
│  - Met/AIC raw provenance text      │
│  - Parallel Search (theft/plunder   │
│    press coverage)                  │
│  - ONE pass, produces EvidenceBundle│
└────────────────────────────────────┘
        │
        │  same EvidenceBundle passed to both
        ▼
┌───────────────────┬───────────────────┐
│ Compliance Auditor │ Provenance        │   ← asyncio.gather,
│ (skeptic)          │ Historian         │      concurrent
│                     │ (advocate)        │
└──────────┬──────────┴─────────┬─────────┘
           │                    │
           ▼                    ▼
        ComplianceAuditorOutput  ProvenanceHistorianOutput
           │                    │
           └────────┬───────────┘
                     ▼
              synthesize_title_risk()
                     │
                     ▼
              TitleRiskMatrix (→ Curator agent)
```

## Interface

```python
# src/artgents/agents/provenance_legal.py

class RetrievedFact(BaseModel):
    claim: str
    source_url: str
    source_type: Literal["wikidata", "met", "aic", "parallel_search"]
    source_entity_id: str | None  # Wikidata QID, AIC object ID, etc.
                                    # None for facts with no single
                                    # identifiable object (most
                                    # Parallel Search hits)

class EvidenceBundle(BaseModel):
    retrieved_facts: list[RetrievedFact]
    query_search_keys: ProvenanceSearchKeys
    evidence_scope: Literal["specific_object", "artist_general"]
    rejected_fact_count: int = 0  # facts dropped due to malformed
                                   # source_url or other validation
                                   # failure during retrieval — surfaces
                                   # silent data loss (e.g. transport-
                                   # level corruption) in the output
                                   # itself, not just in logs a judge
                                   # won't see

class ComplianceAuditorOutput(BaseModel):
    identified_gaps: list[OwnershipGap]  # window, is_high_risk_period: bool
    risk_level: Literal["low", "moderate", "red_flag",
                         "cannot_determine_insufficient_object_data"]
    reasoning: str

class ProvenanceHistorianOutput(BaseModel):
    contextual_notes: str
    cited_evidence: list[RetrievedFact]  # every fact referenced in
                                          # contextual_notes, in EITHER
                                          # direction — not limited to
                                          # exculpatory evidence
    risk_level: Literal["low", "moderate", "red_flag",
                         "cannot_determine_insufficient_object_data"]

class TitleRiskMatrix(BaseModel):
    compliance_auditor: ComplianceAuditorOutput
    provenance_historian: ProvenanceHistorianOutput
    evidence_bundle: EvidenceBundle
    requires_human_review: bool
    synthesis_summary: str  # short synthesized read, states agreement
                             # or disagreement explicitly — does not
                             # average away a disagreement

async def gather_evidence(search_keys: ProvenanceSearchKeys) -> EvidenceBundle:
    ...

async def run_compliance_auditor(bundle: EvidenceBundle) -> ComplianceAuditorOutput:
    ...

async def run_provenance_historian(bundle: EvidenceBundle) -> ProvenanceHistorianOutput:
    ...

async def assess_provenance(search_keys: ProvenanceSearchKeys) -> TitleRiskMatrix:
    bundle = await gather_evidence(search_keys)
    auditor_result, historian_result = await asyncio.gather(
        run_compliance_auditor(bundle),
        run_provenance_historian(bundle),
    )
    return synthesize_title_risk(auditor_result, historian_result, bundle)
```

## Prompt guidance: when to use cannot_determine_insufficient_object_data

Both sub-agent prompts must explicitly instruct: when
`evidence_scope == "artist_general"` and the retrieved evidence cannot
be tied to the specific object being assessed (no shared
`source_entity_id`, no title match), the correct `risk_level` is
`"cannot_determine_insufficient_object_data"` — not a forced guess at
`low`/`moderate`/`red_flag`. Ground this in the same logic real museum
provenance review uses (per AAM/AAMD guidelines): risk assessment
requires knowing whether THIS object meets specific criteria (created
pre-1946, acquired post-1932, changed hands 1933-1945, plausibly in
continental Europe) — without that object-specific data, the honest
answer is that the standard test cannot be applied, not a comfortable
default. This applies independently to each sub-agent; one may reach
this state while the other has grounds for a real judgment (e.g. if
literally every retrieved work by the artist shares one clear pattern).

## Model call configuration

`run_compliance_auditor()` and `run_provenance_historian()` each make
their own independent Vertex AI call. Per `config/agents.yaml`,
`temperature` and `max_output_tokens` for `provenance_legal` apply
**individually to each of these two calls** — not as a shared budget
split across the pair. Each sub-agent gets the full configured
`max_output_tokens` (4096) for its own call.

## Parallel Search integration — placement and scope

Parallel Search is called **only inside `gather_evidence()`**, not by
either sub-agent directly. This is the single retrieval stage described
in `requirements.md` and `structure.md`'s dual-agent architecture
section.

Query construction: use `search_keys.search_keywords` plus targeted
terms for known theft/plunder registries, e.g.:
```
"{primary_artist_attribution}" stolen OR looted OR plunder site:fbi.gov
  OR site:archives.gov OR site:wikipedia.org
```
Results are parsed into `RetrievedFact` entries with `source_type:
"parallel_search"` and the actual result URL — never a claim without
a URL.

**Input robustness:** before building the query, filter
`search_keywords` to drop empty/placeholder strings. If the remaining
identifying terms are insufficient (no usable title or artist term),
skip the Parallel Search call entirely for that request rather than
querying on bare generic terms alone — this was observed to produce
irrelevant results (e.g. unrelated FBI press pages, unrelated museum
provenance records for different objects) when tested against a
request with weak/empty search keys. Log this skip at INFO, don't
silently proceed with a degenerate query.

**Relevance filtering:** after retrieval, drop any Parallel Search
result that shares no keyword overlap with the artwork's own
identifying terms (title, artist, or non-empty search keywords) before
adding it to `retrieved_facts`. A simple keyword-overlap check is
sufficient here — this doesn't need to be another model call, just a
filter on the retrieval layer, consistent with `synthesize_title_risk()`
also being kept as plain logic rather than an LLM call.

Cost note: this is the primary Parallel Search consumer in the
pipeline (Financial Valuation will be the second, in its own retrieval
stage). Both agents' retrieval stages should share the underlying
`src/artgents/clients/parallel.py` client, built once here.

## Client: `src/artgents/clients/parallel.py`

New shared client, built as part of this agent's implementation (first
consumer). Thin wrapper: takes a query string, returns parsed results
with URLs. Does not contain agent-specific query-construction logic —
that stays in each agent's `retrieval.py`/`gather_evidence()`, per the
existing convention (agents own their query shape; clients are dumb
transport + parsing).

## Synthesis logic

`synthesize_title_risk()` is deliberately NOT an LLM call — it's plain
Python logic that:
- Sets `requires_human_review = True` if `risk_level` differs between
  the two sub-agents, OR either is `"red_flag"`, OR either is
  `"cannot_determine_insufficient_object_data"` — the last case is
  inherently review-worthy: "the system can't answer this without more
  information" is not a clean, safe-to-skip result, even though it
  isn't a red_flag either.
- Writes `synthesis_summary` by comparing the two `risk_level` values
  and stating explicitly whether they agree or disagree — this can be
  simple templated text, not a third model call, to avoid introducing
  a third opinion that muddies rather than clarifies the two-agent
  contrast. When either sub-agent's `risk_level` is
  `"cannot_determine_insufficient_object_data"`, the summary states
  this plainly and distinctly from a disagreement — e.g. "One or both
  assessments could not be completed without object-specific data;
  standard due-diligence practice (see AAM/AAMD guidelines) would
  require further research before this question can be answered" —
  rather than folding it into the same phrasing used for a genuine
  risk_level disagreement between two completed assessments.

## Error handling

- Any retrieval source failing (Wikidata timeout, Parallel Search
  error, Met/AIC unavailable) → log at ERROR, continue with partial
  evidence from the sources that succeeded rather than failing the
  whole request — an incomplete evidence bundle is still useful;
  `EvidenceBundle` should make it clear which sources contributed
- If Parallel Search account credit is exhausted → typed error,
  surfaced clearly (not silently treated as "no results found") since
  those are different situations for a caller to handle

## Downstream impact — flagged for follow-up, not handled in this spec

This schema change ripples beyond this agent:
- **API layer** (`AnalyzeResponse`): `compliance_auditor`/
  `provenance_historian` risk_level fields need to accept the new
  literal value — check `response_models.py` reuses the real
  `ComplianceAuditorOutput`/`ProvenanceHistorianOutput` types directly
  (per the API design's existing convention) rather than redeclaring
  the enum, so this may already propagate automatically; confirm
  rather than assume.
- **Frontend** (`DualAgentCard`): currently has three risk-level badge
  states (low/moderate/red_flag styling). Needs a fourth visual state
  for `cannot_determine_insufficient_object_data` — distinct from all
  three existing colors, since it's not "safe" (low), not "concerning"
  (moderate/red_flag), but "unanswerable without more data." A neutral
  color (e.g. grey/blue) with explanatory copy is more honest than
  forcing it into the existing red/amber/green-style spectrum.
- **Curator**: the disclosure-floor logic already keys off
  `requires_human_review`, which this change correctly sets — no
  Curator-side schema change needed, but worth confirming its prompt
  doesn't mischaracterize a `cannot_determine` state as if it were a
  `moderate` finding when narrating.

## Testing approach

- Unit tests mock Wikidata, Met/AIC, and Parallel clients; assert
  `EvidenceBundle` construction, both sub-agent outputs (mocked model
  responses), and `synthesize_title_risk()` logic directly (this one
  is pure Python, should be trivial to test exhaustively — all
  combinations of risk_level pairs)
- One integration test (marked separately) using a real Wikidata query
  and a real, known-documented case if one can be found in Wikidata's
  provenance data (e.g. a work with a documented WWII-era gap) — run
  manually, not in default CI