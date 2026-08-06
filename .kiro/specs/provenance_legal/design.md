# Design: Provenance & Legal Agent

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

class EvidenceBundle(BaseModel):
    retrieved_facts: list[RetrievedFact]
    query_search_keys: ProvenanceSearchKeys  # what was searched for, for traceability

class ComplianceAuditorOutput(BaseModel):
    identified_gaps: list[OwnershipGap]  # window, is_high_risk_period: bool
    risk_level: Literal["low", "moderate", "red_flag"]
    reasoning: str

class ProvenanceHistorianOutput(BaseModel):
    contextual_notes: str
    supporting_evidence: list[RetrievedFact]
    risk_level: Literal["low", "moderate", "red_flag"]

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
  the two sub-agents, OR either is `"red_flag"`
- Writes `synthesis_summary` by comparing the two `risk_level` values
  and stating explicitly whether they agree or disagree — this can be
  simple templated text, not a third model call, to avoid introducing
  a third opinion that muddies rather than clarifies the two-agent
  contrast

## Error handling

- Any retrieval source failing (Wikidata timeout, Parallel Search
  error, Met/AIC unavailable) → log at ERROR, continue with partial
  evidence from the sources that succeeded rather than failing the
  whole request — an incomplete evidence bundle is still useful;
  `EvidenceBundle` should make it clear which sources contributed
- If Parallel Search account credit is exhausted → typed error,
  surfaced clearly (not silently treated as "no results found") since
  those are different situations for a caller to handle

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