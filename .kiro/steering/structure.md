# Structure & Conventions: Artgents

## Repository layout

```
├── README.md
├── .kiro/
│   ├── specs/
│   │   ├── visual_art_historian/
│   │   │   ├── requirements.md
│   │   │   ├── design.md
│   │   │   └── tasks.md
│   │   ├── provenance_legal/
│   │   ├── financial_valuation/
│   │   └── curator/
│   ├── steering/
│   │   ├── product.md
│   │   ├── tech.md
│   │   └── structure.md
│   └── hooks/
├── config
│   └── agents.yaml           # per-agent config: model, prompts, endpoints
├── frontend
├── pyproject.toml
├── src
│   └── artgents
│       ├── __init__.py
│       ├── agents
│       │   ├── __init__.py
│       │   ├── art_historian.py
│       │   ├── provenance_legal.py
│       │   ├── financial_valuation.py
│       │   └── curator.py
│       ├── clients
│       │   ├── __init__.py
│       │   ├── vertex.py
│       │   ├── wikidata.py
│       │   ├── met.py
│       │   ├── aic.py
│       │   └── parallel.py
│       ├── logging_config.py
│       └── pipeline.py
├── tests
└── uv.lock
```

## Conventions

- One module per agent under `agents/`. Each agent exposes a single
  well-defined entrypoint function/class consumed by `pipeline.py` —
  agents do not call each other directly.
- One module per external data source under `clients/`. Clients return
  parsed, typed (Pydantic) results — no raw dict passing between layers.
- `pipeline.py` is the only place that sequences agent calls. Keep agent
  logic and orchestration logic separate.
- All agent outputs that make a factual claim about provenance or
  valuation must carry a `source_url` field. This is enforced at the
  Pydantic model level, not just by convention.
- Config values (model names, API base URLs) live in `config/`, not
  hardcoded in agent modules — keeps `.kiro/steering/tech.md` and the
  actual code from drifting apart.

  ## Dual-agent architecture (Provenance/Legal, Financial Valuation)
 
  These two agents follow a shared pattern, distinct from Visual Art
  Historian and Curator:
  
  1. **Retrieval stage (shared, runs once):** external data sources
    (Wikidata, Met/AIC, Parallel Search) are queried a single time,
    producing one evidence bundle. Every retrieved fact carries a
    `source_url`.
  2. **Dual reasoning stage (concurrent, `asyncio.gather`):** two
    sub-agents reason over the same retrieved evidence bundle and
    produce deliberately contrasting outputs (skeptic vs. advocate;
    conservative vs. bullish). Both always run — this is not a
    user-selectable variant.
  3. **Synthesis:** the two sub-agent outputs are combined into a single
    structured result (title risk matrix; valuation corridor) — not
    just concatenated, and not averaged into a single number that
    erases the disagreement.
  Retrieval is shared specifically so that disagreement between the two
  sub-agents comes from interpreting the same evidence differently,
  not from each side finding different facts — this mirrors how real
  adversarial review works (a title attorney and a historian look at the
  same documented gap and disagree about how much it matters).
  
  This is different from Curator's `variants`, which are selectable (one
  chosen per run) rather than concurrent — see `config/agents.yaml` for
  the distinction.

  ## Reuse over re-run
 
When a request parameter only affects the LAST stage of a multi-stage
pipeline (e.g. Curator's `variant_key`), do not re-run earlier stages
just to satisfy that parameter. Compute all variants of the final
stage's output in one pipeline execution, reusing the same upstream
results, rather than requiring a full re-run per variant. This applies
generally, not just to Curator: if a future parameter is ever added
that only affects one stage, prefer computing all its variants
up front over making the caller pay for a full re-run to change one
thing at the end.

## Testing conventions

- Tests mirror the `src/artgents/` structure 1:1 under `tests/`
  (e.g. `tests/agents/test_art_historian.py`)
- External API calls are mocked in unit tests; a small set of
  integration tests hitting real endpoints (Wikidata, Met, AIC) are kept
  separate and clearly marked, since they depend on network access and
  third-party uptime