# Design: Curator Agent

## Architecture

```
VisualAnalysisOutput + TitleRiskMatrix + FinancialValuationResult
+ optional variant_key
        │
        ▼
┌────────────────────────────────────┐
│ curator.py                          │
│  - load variant config              │
│  - compute mandatory disclosures    │
│    (plain Python, not LLM)          │
│  - build prompt (variant-scoped     │
│    content inclusion)               │
│  - call Gemini via Vertex           │
│  - validate/parse response          │
└────────────────────────────────────┘
        │
        ▼
  CuratorOutput (Pydantic)
```

Single agent, single model call — no dual-agent split here (this is a
synthesis/narration task, not an adversarial-judgment task like
Provenance/Legal or Financial Valuation).

## Interface

```python
# src/artgents/agents/curator.py

class CuratorInput(BaseModel):
    visual_analysis: VisualAnalysisOutput
    title_risk: TitleRiskMatrix
    valuation: FinancialValuationResult
    variant_key: str | None = None  # None -> use YAML default_variant

class CuratorModelResponse(BaseModel):
    """Schema the model actually fills in via structured output.
    Deliberately does NOT include `disclosures` — see 'Mandatory
    disclosure floor' below for why."""
    exhibition_narrative: str
    wall_label: str
    suggested_title: str

class CuratorOutput(BaseModel):
    """Final output returned by curate(). `disclosures` is assigned in
    Python from determine_disclosures()'s return value, never from the
    model's own output."""
    exhibition_narrative: str
    wall_label: str
    suggested_title: str
    disclosures: list[str]
    variant_used: str

async def determine_disclosures(
    title_risk: TitleRiskMatrix,
    valuation: FinancialValuationResult,
    variant: str,
) -> list[str]:
    """Plain Python, NOT an LLM call — same principle as
    synthesize_title_risk() and synthesize_valuation(). The disclosure
    floor is a compliance-critical check; it must not depend on the
    model choosing to mention it. Computed BEFORE the prompt is built,
    then injected into the prompt as required content the model must
    reference in its prose. The model's response schema
    (CuratorModelResponse) does not include a disclosures field at
    all — curate() assigns CuratorOutput.disclosures directly from this
    function's return value after the model call, never from model
    output."""
    ...

async def curate(input: CuratorInput) -> CuratorOutput:
    ...
```

## Disclosure floor — computed in code, not left to the model

`determine_disclosures()` runs first, before any model call:

```python
disclosures = []
if title_risk.requires_human_review:
    if variant == "auction_house":
        disclosures.append(
            f"Provenance: {title_risk.synthesis_summary}"
        )
    else:  # public_gallery
        disclosures.append(
            "This work's provenance is undergoing further review."
        )
if valuation.requires_human_review:
    if variant == "auction_house":
        disclosures.append(
            f"Valuation: {valuation.corridor_summary}"
        )
    else:
        disclosures.append(
            "This work's market valuation carries significant "
            "uncertainty pending further research."
        )
```

This list is then passed INTO the prompt as content the model MUST
reference naturally within `exhibition_narrative`/`wall_label` prose —
the model doesn't decide whether to surface it, only how to phrase the
surrounding narrative.

**Critical implementation detail:** `CuratorOutput.disclosures` is NOT
a field the model fills in as part of its structured output. The
model's response schema should NOT include a `disclosures` field at
all — only `exhibition_narrative`, `wall_label`, and `suggested_title`
come from the model. After the model call returns, `curate()` sets
`disclosures` directly to the return value of `determine_disclosures()`
computed earlier, in Python. This was found necessary in testing: an
earlier version let the model populate `disclosures` as part of its own
structured output (even while being fed the code-computed list as
prompt guidance), and the model added an extra, code-uncomputed
disclosure on one run. That's proof the field wasn't a true structural
guarantee — a looseness that could just as easily drop a required
disclosure on a different run, silently. Removing `disclosures` from
the model's response schema entirely, and assigning it directly in
Python, is the only way to make it unconditionally correct rather than
usually correct.

This mirrors the design principle used throughout this project:
anything compliance-critical (source URLs, risk flags, confidence
hedging) is enforced structurally, not left to prompt-following alone,
because prompt-following alone has already been shown to fail in
exactly this kind of "is this important enough to include, and did I
include exactly the right set" judgment call (see Provenance/Legal's
`cited_evidence` bug, which had the same root cause: an important fact
was in the model's context but had no structural guarantee of
surfacing in the output).

## Variant-scoped content inclusion

The prompt itself differs by variant, not just voice:
- `auction_house`: includes `valuation.valuation_corridor` and
  `valuation.corridor_summary` as content to weave into
  `exhibition_narrative`/`wall_label`.
- `public_gallery`: explicitly instructed NOT to include dollar figures
  in `exhibition_narrative`/`wall_label` — financial content is
  omitted from prose (though the disclosure floor above still applies
  regardless of variant, via the softer public-facing phrasing).

## Hedge-language preservation

Prompt explicitly instructs: any attribution, period, or provenance
claim from `visual_analysis.search_keys` or `title_risk` that was
phrased as hedged/attributed ("Attributed to...", "moderate
confidence", disputed) must be preserved as hedged in the output
prose — not smoothed into confident narrative language. This is the
same principle validated repeatedly in Visual Art Historian and
Provenance/Legal testing: fluent prose should not imply more certainty
than the underlying finding actually has.

## Category precision — do not conflate provenance risk with authenticity

Testing surfaced a real instance of category-bleed: `auction_house`
wall label copy described a `TitleRiskMatrix` disagreement (a
provenance/ownership-gap finding) as "authenticity and title
challenges" — but no upstream agent raised any authenticity concern in
that run. `TitleRiskMatrix` findings are about ownership history and
documented gaps; they are NOT a statement about whether the work is
genuinely by the attributed artist. Authenticity/attribution confidence
is exclusively Visual Art Historian's domain
(`stylistic_authenticity_notes`, and the hedge on
`primary_artist_attribution`).

The prompt must explicitly instruct the model: when describing
`TitleRiskMatrix` findings, use "provenance" or "title" language only
— never "authenticity," "genuine," "attribution risk," or similar terms
that belong to Visual Art Historian's findings, unless Visual Art
Historian's own output actually raised such a concern. Do not rely on
the model naturally keeping these separate — this conflation happened
even with a functioning, well-tested model call, so it needs an
explicit guard.

## Config loading

Uses `config_loader.get_selectable_variant_config("curator",
variant_key)` — falls back to YAML `default_variant`
(`public_gallery`) when `variant_key` is `None`; an explicitly invalid
`variant_key` raises rather than silently defaulting (per
`config_loader.py`'s existing behavior, already built and tested).

## Model call

- Temperature/max_output_tokens from the loaded variant config (0.6 /
  2048 per `agents.yaml`)
- Structured output via schema-constrained generation, same pattern as
  all other agents

## Error handling

- Missing/malformed upstream input (e.g. a required field absent) ->
  typed validation error before any model call, not a wasted API call
- Vertex AI call failure -> propagate typed error to `pipeline.py`

## Testing approach

- Unit tests: `determine_disclosures()` tested exhaustively over all
  four combinations of the two `requires_human_review` booleans, for
  both variants (8 cases total) — this is the compliance-critical
  logic and should have zero ambiguity in its test coverage
- Unit tests: variant-scoped content inclusion (auction_house includes
  valuation figures, public_gallery excludes them) — mocked model
  responses
- Unit tests: hedge-language preservation — given a mocked upstream
  input with a hedged attribution, assert the prompt sent to the model
  includes the hedging instruction (or, if feasible, assert on a mocked
  response that hedged language survives)
- One integration test (marked separately): a full run using real
  outputs from the other three agents (or realistic fixtures modeled on
  them) against live Vertex AI