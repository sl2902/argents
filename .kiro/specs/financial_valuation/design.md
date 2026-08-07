# Design: Financial Valuation Agent

## Architecture

```
ProvenanceSearchKeys (from Visual Art Historian)
+ optional TitleRiskMatrix (from Provenance/Legal)
        │
        ▼
┌────────────────────────────────────┐
│ retrieval.py / gather_comps()       │
│  - Parallel Search (auction press,  │
│    news, comparable sales)          │
│  - Wikidata sale-price properties   │
│    (P2296/P1088)                    │
│  - ONE pass, produces               │
│    ComparableSalesEvidence          │
└────────────────────────────────────┘
        │
        │  same evidence passed to both
        ▼
┌───────────────────┬───────────────────┐
│ Conservative        │ Bullish           │   ← asyncio.gather,
│ Appraiser (floor)   │ Specialist        │      concurrent
│                     │ (ceiling)         │
└──────────┬──────────┴─────────┬─────────┘
           │                    │
           ▼                    ▼
   ConservativeAppraiserOutput  BullishSpecialistOutput
           │                    │
           └────────┬───────────┘
                     ▼
           synthesize_valuation()
                     │
                     ▼
           ValuationCorridor (→ Curator agent)
```

## Evidence scope — reused pattern from Provenance/Legal

Same concept, same field names where applicable, for consistency across
the two dual-agent agents:

- `ComparableSale.source_entity_id: str | None` — mirrors
  `RetrievedFact.source_entity_id`. Populated with a Wikidata QID when
  a specific sold work is identifiable; `None` for news-article comps
  with no single identifiable work.
- `ComparableSalesEvidence.evidence_scope: Literal["specific_object",
  "artist_general"]` — set identically to Provenance/Legal's logic:
  `"specific_object"` only when `work_title` is known and matched to a
  single entity; `"artist_general"` otherwise.
- In `"artist_general"` mode, both sub-agent prompts must be told
  explicitly (same instruction pattern as Provenance/Legal's
  Compliance Auditor / Provenance Historian prompts): comps may
  represent many different works by this artist, not this specific
  piece — frame the estimate as "this artist's general market range,"
  not "this artwork is worth X."

## Interface

```python
# src/artgents/agents/financial_valuation.py

class ComparableSale(BaseModel):
    description: str
    price_usd: float | None  # None if source doesn't give a clear
                               # figure — should never be fabricated
    sale_date: str | None
    source_url: str
    source_entity_id: str | None
    source_type: Literal["wikidata", "parallel_search"]

class ComparableSalesEvidence(BaseModel):
    comparable_sales: list[ComparableSale]
    query_search_keys: ProvenanceSearchKeys
    evidence_scope: Literal["specific_object", "artist_general"]
    rejected_fact_count: int = 0  # same pattern as Provenance/Legal —
                                    # comps dropped due to malformed
                                    # source_url or validation failure

class ConservativeAppraiserOutput(BaseModel):
    floor_estimate_usd: float
    methodology: str
    confidence: Literal["low", "moderate", "high"]

class BullishSpecialistOutput(BaseModel):
    ceiling_estimate_usd: float
    methodology: str
    confidence: Literal["low", "moderate", "high"]

class ValuationCorridor(BaseModel):
    low_estimate_usd: float
    high_estimate_usd: float

class FinancialValuationResult(BaseModel):
    conservative_appraiser: ConservativeAppraiserOutput
    bullish_specialist: BullishSpecialistOutput
    evidence: ComparableSalesEvidence
    valuation_corridor: ValuationCorridor
    corridor_summary: str
    requires_human_review: bool

async def gather_comps(
    search_keys: ProvenanceSearchKeys,
) -> ComparableSalesEvidence:
    ...

async def run_conservative_appraiser(
    evidence: ComparableSalesEvidence,
    title_risk: TitleRiskMatrix | None = None,
) -> ConservativeAppraiserOutput:
    ...

async def run_bullish_specialist(
    evidence: ComparableSalesEvidence,
) -> BullishSpecialistOutput:
    ...

async def assess_valuation(
    search_keys: ProvenanceSearchKeys,
    title_risk: TitleRiskMatrix | None = None,
) -> FinancialValuationResult:
    evidence = await gather_comps(search_keys)
    conservative, bullish = await asyncio.gather(
        run_conservative_appraiser(evidence, title_risk),
        run_bullish_specialist(evidence),
    )
    return synthesize_valuation(conservative, bullish, evidence)
```

Note `title_risk` is only threaded into the Conservative Appraiser, not
the Bullish Specialist — a documented title dispute is a legitimate
reason to discount the floor estimate (marketability risk), but isn't
something the ceiling/replacement-value framing needs to account for in
the same way. This is a deliberate asymmetry, not an oversight — flag
back if this seems wrong once building starts.

## Model call configuration

Per `config/agents.yaml`, `temperature` and `max_output_tokens` for
`financial_valuation` apply **individually to each of the two sub-agent
calls** — same as Provenance/Legal, not a shared budget. Load via
`config_loader.get_dual_agent_config("financial_valuation")`.

## Parallel Search integration — reuse existing hardening

Called only inside `gather_comps()`, following the exact same hardening
already built for Provenance/Legal — do not reimplement, reuse the
existing filtering logic if it can be shared, or replicate the pattern
exactly if the code isn't structured for direct reuse:
- Filter empty/placeholder terms from `search_keywords` before querying
- Skip the call entirely if no usable anchor (artist/title/keyword)
  remains after filtering
- Apply a relevance filter on results before adding to
  `comparable_sales` — a result must share keyword overlap with the
  artwork's identifying terms

Query construction should target auction/sale-price language
specifically, e.g.:
```
"{primary_artist_attribution}" sold OR "sale price" OR auction
  site:artnet.com OR site:christies.com OR site:sothebys.com
  OR site:reuters.com
```
(sites listed are illustrative — actual domain targeting can be tuned
during implementation)

## Wikidata integration — reuse existing client-level LIMIT

Uses `WikidataClient` (already built for Provenance/Legal, with a
default `LIMIT` applied when a query doesn't specify one) — query
targets `P2296`/`P1088` (sale price properties) rather than ownership
history. Reuse the client, don't build a second one.

## Synthesis logic

`synthesize_valuation()` is plain Python, NOT an LLM call — same
reasoning as `synthesize_title_risk()`: preserve the two-estimate
contrast rather than average it away with a third opinion.

- `low_estimate_usd = conservative.floor_estimate_usd`
- `high_estimate_usd = bullish.ceiling_estimate_usd`
- `requires_human_review = True` if:
  - `evidence.evidence_scope == "artist_general"` AND
    `len(evidence.comparable_sales) < 3` (sparse comps), OR
  - both sub-agents' `confidence == "low"`
- `corridor_summary` states the range in plain language and explicitly
  flags if the floor-to-ceiling spread is unusually wide (e.g. ceiling
  more than ~3x floor) rather than presenting a wide spread silently as
  if it were an ordinary, expected result

## Error handling

- Any retrieval source failing → log at ERROR, continue with partial
  evidence from sources that succeeded (same pattern as
  Provenance/Legal's `gather_evidence()`)
- Malformed `source_url` on a comp → drop the comp, increment
  `rejected_fact_count`, log at WARNING (same pattern as
  Provenance/Legal)

## Testing approach

- Unit tests mock Wikidata and Parallel clients; assert
  `ComparableSalesEvidence` construction (including `evidence_scope`
  logic — reuse/mirror the Provenance/Legal test cases for
  specific_object vs. artist_general), both sub-agent outputs (mocked
  model responses), and `synthesize_valuation()` logic directly
  (exhaustive over confidence/scope combinations, same rigor as
  `synthesize_title_risk()`'s tests)
- One integration test (marked separately) using a real artist/title
  combination with genuinely findable public sale price coverage