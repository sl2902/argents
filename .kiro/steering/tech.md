# Tech Stack: Artgents

## Language & packaging

- Python >= 3.12
- `uv` for dependency management and locking (`uv.lock`)
- `src` layout: all importable code lives under `src/artgents/`
- `setuptools` build backend, package discovery via
  `[tool.setuptools.packages.find] where = ["src"]`

## Core dependencies

- `fastapi` + `uvicorn` — backend API serving the pipeline and frontend
- `pydantic` + `pydantic-settings` — structured agent I/O and config
- `httpx` — all outbound HTTP: Wikidata SPARQL, Met API, AIC API, Parallel
  Search
- `loguru` — logging
- `google-genai` — model client, used against **Vertex AI**
  (`vertexai=True`), not the AI Studio Gemini Developer API

## Models

- **Primary:** Gemini via Vertex AI (project-based, billed against Google
  Cloud credit). Chosen specifically to avoid the AI Studio free-tier rate
  limits (5–15 RPM), which are too low for a live multi-agent demo.
- **Fallback (manual, not auto-routed):** Gemma 4 self-hosted on Cloud Run.
  Enabled via a config flag, not automatic failover. Documented as a
  fallback path in the README, not exercised by default.
- The AI Studio Gemini Developer API (api key based, ai.google.dev) is
  intentionally NOT used as the primary path.

## External data sources

- **Wikidata** — SPARQL queries via raw HTTP POST to
  `query.wikidata.org/sparql` using `httpx`, requesting
  `application/sparql-results+json`. No dedicated SPARQL client library;
  kept as a thin wrapper to avoid an extra dependency.
- **The Met Museum API** — public REST/JSON, no auth required. Two
  operational notes, discovered during testing, apply to every client
  calling this API:
  - The API sits behind Incapsula bot protection and returns 403 for
    requests without a realistic browser-like `User-Agent` header.
    Clients must set one explicitly and consistently — not just for ad
    hoc/manual testing.
  - Not every object has a usable image: `isPublicDomain` may be
    `false`, and even when metadata exists, `primaryImage` /
    `primaryImageSmall` may be empty strings for rights-restricted
    works. Any client consuming Met objects must check both
    `isPublicDomain: true` and a non-empty `primaryImage` before
    attempting to use an object's image — do not assume every returned
    object has a downloadable image.
- **Art Institute of Chicago API** — public REST/JSON, no auth required.
- **Parallel Search API** — used for open-web retrieval of public auction
  press coverage and stolen-art press releases. Cited by URL in agent
  output. Credit-based pricing; current account has promotional credits
  sufficient for the judging window (documented in README, not assumed
  to be free for a fresh account).
All three museum/provenance data sources and Parallel are called through
thin client wrappers in `src/artgents/clients/`, not through a shared
generic HTTP helper — keeps each source's query shape and response
parsing independent and easy to reason about per agent.

## Testing

- `pytest`, `pytest-asyncio`, `pytest-cov`
- `diagrams` (dev-only) for architecture diagrams in documentation

## Deployment

- Backend: Cloud Run
- Frontend: Vercel (TBD)