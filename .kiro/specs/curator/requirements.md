# Requirements: Curator Agent

## Purpose

Synthesize the outputs of all three upstream agents — Visual Art
Historian, Provenance/Legal, and Financial Valuation — into
publication-ready exhibition copy: a longer narrative piece and a short
wall label, in one of two voices (Auction House Cataloguer or Public
Gallery Docent).

This agent runs LAST in the pipeline, after all three other agents have
completed. It does not retrieve any external data and does not make
factual claims of its own — it synthesizes and narrates, it does not
investigate.

## User stories

1. As a gallery curator preparing an exhibition, I get publication-
   ready wall label copy in an approachable voice, so I'm not starting
   from a blank page for each piece.

2. As an auction house cataloguer, I get formal catalog copy that
   includes the estimate range and provenance disclosures I'm required
   to publish, in the correct register for a specialist/bidder
   audience.

3. As anyone reading this copy, I trust that it doesn't overstate
   certainty the upstream agents didn't have — if Visual Art Historian
   hedged an attribution, or Provenance/Legal flagged an unresolved
   title question, or Financial Valuation's estimate came with a wide
   spread and a human-review flag, that uncertainty is preserved in
   the copy, not smoothed into confident prose for a better story.

## Inputs

- `VisualAnalysisOutput` fields: `composition_analysis`,
  `condition_notes`, `stylistic_authenticity_notes`, plus
  `search_keys` (for attribution/period/style, with its existing hedge
  language — e.g. "Attributed to..." — intact)
- `TitleRiskMatrix` (from Provenance/Legal): `synthesis_summary`,
  `requires_human_review`, both sub-agents' `risk_level`
- `FinancialValuationResult` (from Financial Valuation):
  `valuation_corridor`, `corridor_summary`, `requires_human_review`
- `variant_key: str | None` — which voice to use; `None` falls back to
  `config/agents.yaml`'s `curator.default_variant` (`public_gallery`)

## Outputs (structured, Pydantic-validated)

- `exhibition_narrative`: string — longer-form piece (composition,
  historical context, provenance story, significance)
- `wall_label`: string — short-form (~50-150 words), suitable for
  physical/digital placement next to the work
- `suggested_title`: string — a display title for the piece if none was
  already known (derived from subject/style, not fabricated as a claim
  of the work's actual historical title)
- `disclosures`: list of string — see "Mandatory disclosure floor"
  below; present regardless of variant, even when the variant's prose
  style wouldn't naturally surface them
- `variant_used`: string — which config variant actually produced this
  output, for traceability

## Content scoping by variant — a real content difference, not just tone

- **`auction_house`**: includes the valuation corridor and its
  `corridor_summary` caveats, and a formal provenance/title-risk
  disclosure, matching standard auction catalog practice (estimates and
  condition/provenance disclosures are expected, published content in
  this context).
- **`public_gallery`**: wall-label copy for general visitors does not
  typically include dollar figures or formal risk-matrix language —
  narrative/historical framing is more appropriate. Financial specifics
  are omitted from `exhibition_narrative`/`wall_label` in this variant.
  This is a deliberate content-scoping decision per variant, not an
  oversight — flag back if this should be reconsidered.

## Mandatory disclosure floor — applies regardless of variant

Regardless of variant, if EITHER `TitleRiskMatrix.requires_human_review`
OR `FinancialValuationResult.requires_human_review` is `true`, that fact
must appear in `disclosures` in plain language appropriate to the
variant's register (e.g. auction_house: cite the specific risk_level/
corridor spread; public_gallery: a softer but still honest note that
provenance or valuation is under further review). **This must never be
silently omitted to preserve a cleaner narrative** — this is the same
principle applied throughout this project: a good story is not a reason
to suppress a real flag raised by an upstream agent.

**`CuratorOutput.disclosures` MUST be set directly from
`determine_disclosures()`'s return value in Python, after the model
call — never trusted from the model's own structured output, even as
part of the same schema the model fills in.** Testing surfaced why this
distinction matters: when `disclosures` was populated by the model
(even when guided by prompt content matching the code-computed list),
the model added an extra, code-uncomputed disclosure on one run — not
wrong in that instance, but proof the field wasn't actually
structurally guaranteed. The same looseness could just as easily drop a
required disclosure on a different run. The model may reference
disclosure content naturally within `exhibition_narrative`/`wall_label`
prose, but the `disclosures` list field itself is a Python-assigned
value, not model output — this is the only way to make it a true
guarantee rather than a usually-correct convention.

## Acceptance criteria

- `exhibition_narrative` and `wall_label` never state an attribution as
  unqualified fact when `search_keys.primary_artist_attribution` (or
  the equivalent hedge in Visual Art Historian's output) was phrased as
  an attribution/hypothesis — the hedge language is preserved, not
  smoothed into confident prose.
- If `TitleRiskMatrix.requires_human_review` or
  `FinancialValuationResult.requires_human_review` is `true`, this is
  present in `disclosures` — verifiable by direct field check, not
  just "usually mentioned in the narrative."
- `auction_house` variant output includes the valuation corridor;
  `public_gallery` variant output does not include dollar figures in
  `exhibition_narrative`/`wall_label`.
- No new factual claims appear in `exhibition_narrative`/`wall_label`
  that aren't traceable to one of the three upstream agents' outputs —
  Curator synthesizes and narrates, it does not introduce new
  attributions, dates, or provenance facts of its own.
- Curator does not conflate the upstream agents' distinct risk
  categories. `TitleRiskMatrix` findings are about ownership history/
  provenance gaps — they must be described as "provenance" or "title"
  concerns, never as "authenticity" concerns. Authenticity/attribution
  confidence is Visual Art Historian's domain
  (`stylistic_authenticity_notes`, hedge language on
  `primary_artist_attribution`) and is a separate claim from whether
  the ownership chain has gaps. Testing surfaced exactly this
  conflation ("authenticity and title challenges" used to describe a
  disagreement that was only ever about provenance/title risk, with no
  authenticity concern raised by any upstream agent) — the prompt must
  guard against it explicitly, not rely on the model naturally keeping
  these separate.
- `variant_used` accurately reflects which config variant was actually
  applied (explicit `variant_key` if provided, else the YAML default).
- Core synthesis logic and the disclosure-floor enforcement are covered
  by unit tests with a mocked model client — the disclosure floor in
  particular should be tested exhaustively (all four combinations of
  the two `requires_human_review` booleans), not exercised only
  manually.
- The agent logs (via `logging_config.py`, not `print()`): which
  variant was used, whether the disclosure floor was triggered, and
  Vertex AI call latency/failures.
- Voice/framing and model parameters are loaded from
  `config/agents.yaml` via
  `config_loader.get_selectable_variant_config("curator", variant_key)`
  — not hardcoded in the agent module.

## Out of scope

- Curator does not re-verify or second-guess upstream findings — it
  trusts and narrates them. If an upstream finding seems wrong, that's
  a bug in the upstream agent, not something for Curator to silently
  "correct" in its prose.
- No image generation — this agent produces text only.