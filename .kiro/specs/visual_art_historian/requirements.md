# Requirements: Visual Art Historian Agent

## Purpose

Given one or more photos of a physical artwork (painting or sculpture),
produce a structured visual/stylistic analysis: likely period/movement,
medium, notable technical features, and a plain-language description
suitable for downstream use by the Curator and Provenance/Legal agents.

This agent supports two distinct use cases:
- **Blind discovery**: no metadata provided (e.g. an unlabeled work found
  in storage) — the agent relies entirely on visual signal.
- **Verification/audit**: metadata is claimed (e.g. "1912 Georges Braque
  Cubist oil painting") — the agent checks whether visual features are
  consistent with the claim, and flags stylistic or material anomalies
  rather than passively confirming it.

## User stories

1. As a gallery researcher, I upload photos of an unlabeled or
   partially-labeled work and receive a structured description of its
   visual characteristics, so I don't have to write this up by hand.

2. As a gallery researcher with a claimed attribution, I upload photos
   along with the claimed artist/period/medium, and the agent tells me
   whether the visual evidence is consistent with that claim or flags
   anomalies — this is a verification task, not just identification.

3. As the Provenance/Legal agent (downstream consumer), I receive
   structured search keys (attribution, creation window, style/movement,
   detected marks, search keywords) so I can query Wikidata, the Met/AIC
   APIs, and Parallel Search precisely instead of searching blind. The
   Visual Art Historian agent runs before I do, not in parallel with me.

4. As the Curator agent (final synthesis step), I receive descriptive,
   evocative language about the work's visual character — merged with
   the Provenance and Financial Valuation agents' findings — to write the
   final exhibition dossier.

## Inputs

- 1–N images of the artwork (required)
- Optional known metadata, if the user has it: artist name, title,
  approximate period, medium (all optional — agent must work with images
  alone if nothing else is provided)

## Outputs (structured, Pydantic-validated)

Output is split into two nested groups, matching the two downstream
consumers:

**`search_keys` (for Provenance/Legal agent — consumed first):**
- `primary_artist_attribution`: string (e.g. "Georges Braque" or
  "Attributed to School of Braque" if uncertain)
- `probable_creation_window`: string (e.g. "1910–1914")
- `style_and_movement`: string (e.g. "Analytic Cubism")
- `detected_signatures_or_marks`: list of strings
- `search_keywords`: list of strings, optimized for Wikidata/Parallel
  Search query construction

**For Curator agent (consumed after Provenance/Legal):**
- `composition_analysis`: string (spatial layout, brushwork, palette)
- `condition_notes`: string (visible damage, craquelure, wear)
- `stylistic_authenticity_notes`: string — for the verification case,
  states whether visual features are consistent with a claimed
  attribution, or flags anomalies; for blind discovery, states stylistic
  confidence generally

## Acceptance criteria

- Given a clear photo of a well-known style (e.g. a Cubist-style oil
  painting) with no metadata, the agent produces reasonable
  `search_keys` without needing user-supplied metadata (blind discovery
  case).
- Given a clear photo with a claimed attribution, the agent explicitly
  states whether visual evidence supports or conflicts with the claim in
  `stylistic_authenticity_notes` (verification case) — it does not simply
  echo the claimed metadata back as fact.
- Given no usable visual signal (e.g. blurry photo, non-artwork image),
  the agent returns low-confidence output rather than a fabricated
  confident guess.
- `primary_artist_attribution` is never stated as unqualified fact unless
  a legible signature is detected; otherwise it is phrased as an
  attribution/hypothesis (e.g. "Attributed to...").
- Output is valid against the agent's Pydantic schema 100% of the time.
- Confidence is calibrated differently for different claim types:
  identifying a general period/style/movement (e.g. "International
  Gothic") may reasonably carry high confidence when visual evidence is
  strong, but attributing the work to a *specific named artist* without
  a legible signature or other direct corroborating evidence must carry
  meaningfully lower confidence language, reflecting that workshop/
  follower attribution is inherently contestable scholarship — not
  treated as equally certain just because the stylistic reasoning behind
  it is well-articulated.
- Output is valid against the agent's Pydantic schema 100% of the time.
- Core parsing/validation logic, both prompt branches (blind discovery
  and verification), and invalid-image handling are covered by unit
  tests using a mocked Vertex client — not exercised only manually.
- The agent logs (via the shared logging_config.py logger, not print()): which prompt 
  branch was taken (blind discovery vs. verification), Vertex AI call latency and any call failures, 
  and whenever output is low-confidence or an anomaly is flagged in 
  stylistic_authenticity_notes — so a run can be debugged from logs 
  alone without re-running the model.
- Agent voice/domain framing and model parameters (temperature,
  max_output_tokens) are loaded from `config/agents.yaml` via the
  shared config loader — not hardcoded in the agent module — so
  changing tone or model parameters doesn't require a code change.

## Out of scope

- Authentication / forgery detection — this agent describes style, it
  does not certify genuineness.
- OCR of provenance labels or gallery placards (handled separately, if
  at all, not by this agent).