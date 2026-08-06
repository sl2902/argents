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

## Testing conventions

- Tests mirror the `src/artgents/` structure 1:1 under `tests/`
  (e.g. `tests/agents/test_art_historian.py`)
- External API calls are mocked in unit tests; a small set of
  integration tests hitting real endpoints (Wikidata, Met, AIC) are kept
  separate and clearly marked, since they depend on network access and
  third-party uptime