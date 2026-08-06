# Design: Visual Art Historian Agent

## Architecture

```
Image(s) + optional metadata
        │
        ▼
┌───────────────────────────┐
│ art_historian.py           │
│  - build multimodal prompt │
│  - call Gemini via Vertex  │
│  - validate/parse response │
└───────────────────────────┘
        │
        ▼
  VisualAnalysisOutput (Pydantic)
        │
        ▼
  search_keys ──► Provenance/Legal agent (runs next, uses search_keys
        │          to query Wikidata/Met/AIC/Parallel Search)
        │
        ▼
  composition_analysis, condition_notes, stylistic_authenticity_notes
        │          (merged with Provenance/Legal and Financial Valuation
        ▼           findings)
     Curator agent (final synthesis — runs last)
```

Note the routing is **sequential, not fan-out**: Provenance/Legal needs
`search_keys` to run its own queries, so it must complete before Curator
synthesizes the final dossier. `pipeline.py` enforces this ordering.

## Interface

```python
# src/artgents/agents/art_historian.py

class VisualAnalysisInput(BaseModel):
    images: list[str] # base64-encoded strings only; 1-N images.
    known_title: str | None = None
    known_artist: str | None = None
    known_period: str | None = None
    medium: str | None = None

class ProvenanceSearchKeys(BaseModel):
    primary_artist_attribution: str
    probable_creation_window: str
    style_and_movement: str
    detected_signatures_or_marks: list[str]
    search_keywords: list[str]

class VisualAnalysisOutput(BaseModel):
    # Downstream Handoff 1: Provenance / Legal agent (consumed first)
    search_keys: ProvenanceSearchKeys

    # Downstream Handoff 2: Curator agent (consumed after Provenance/Legal)
    composition_analysis: str
    condition_notes: str
    stylistic_authenticity_notes: str

async def analyze_artwork(input: VisualAnalysisInput) -> VisualAnalysisOutput:
    ...
```

## Model call

- Client: `src/artgents/clients/vertex.py` (shared across agents)
- Model: Gemini via Vertex AI, multimodal (image + text) input
- Use Pydantic-constrained structured output (via `response_schema` or
  equivalent) rather than free-text parsing — this is what makes the
  100%-schema-validity acceptance criterion achievable, not just aspirational
- Prompt must branch on whether metadata was supplied:
  - **Blind discovery** (no metadata): ask the model to identify from
    visual evidence alone.
  - **Verification** (metadata supplied): ask the model to explicitly
    assess whether visual evidence is *consistent with* the claim, and
    to state anomalies if found — not to passively restate the claim as
    confirmed.
- When multiple images are supplied, treat them as multiple views of the
  same physical work (e.g. full front, signature close-up, back/canvas
  condition) — all images go into a single multimodal call so the model
  can cross-reference them (e.g. confirm a signature seen in a close-up
  against the overall style seen in the full view), not N separate calls
  merged afterward.
- Prompt explicitly instructs: `primary_artist_attribution` must be
  phrased as an attribution ("Attributed to...") unless a legible
  signature is visible in the image.
- Prompt explicitly separates two kinds of confidence and instructs the
  model not to conflate them:
  - Confidence in **period/style/movement** identification — can be
    high when visual evidence (technique, materials, iconography) is
    strong and characteristic of a well-defined period.
  - Confidence in **attributing to one specific named artist** — must
    default to moderate-to-low unless there is direct corroborating
    evidence (legible signature, documented provenance passed in as
    known metadata). A well-reasoned stylistic argument for a specific
    artist is not the same as certainty, and the model must not let
    fluency of its own reasoning inflate the stated confidence.

## Logging
 
Uses the shared logger from `src/artgents/logging_config.py` — no
`print()` calls. Log points:
 
- Which prompt branch was taken (`blind_discovery` or `verification`),
  logged at INFO
- Vertex AI call latency, logged at INFO/DEBUG; call failures logged at
  ERROR with enough context to retry (image ref, input metadata, but not
  the raw image bytes)
- Low-confidence output or a flagged anomaly in
  `stylistic_authenticity_notes`, logged at WARNING — this is an
  expected outcome, not an error, but should be visible in logs without
  re-running the model to notice it

## Error handling

- No usable image (corrupt file, non-image upload) -> return a clear
  validation error before calling the model, not a wasted API call
- Vertex AI call failure -> propagate a typed error up to `pipeline.py`;
  pipeline decides whether to surface partial results or fail the whole
  run (decision belongs in `pipeline.py` design, not here)
- Low-confidence output is a valid, expected result — not an error state

## Testing approach

- Unit tests mock the Vertex client and assert:
  - schema validation on well-formed mock responses
  - graceful handling of a mock low-confidence response
  - rejection of invalid/corrupt image input before any model call
- One integration test (marked separately, per structure.md convention)
  using a real, small, known public-domain image (e.g. a Met Open Access
  image) run against the real Vertex endpoint, to confirm the full path
  works end-to-end — not run in CI by default, run manually before demo
  recording