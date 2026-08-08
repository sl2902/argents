# Requirements: Frontend

## Purpose

A React/Vite frontend for Artgents that showcases the four-agent
pipeline visibly — upload flow, per-stage loading/progress, and a
results view built around the same principle as the API layer: show
both sub-agents' reasoning at each dual-agent stage, not just a
synthesized verdict.

## User stories

1. As a demo viewer, I upload a photo and can see the app work through
   four distinct stages, not just a single spinner — so the
   multi-agent architecture is visible in the experience, not just in
   the code.

2. As a demo viewer, I can see the Compliance Auditor and Provenance
   Historian's assessments side by side, and see clearly if they
   disagree — same for Conservative Appraiser vs. Bullish Specialist —
   because that visible disagreement is the actual point of this
   project's architecture.

3. As a user, I can toggle between Auction House and Public Gallery
   voice and see the exhibition copy change accordingly, including
   real content differences (dollar figures present/absent), not just
   tone.

4. As a user, if my upload isn't recognized as an artwork, I get a
   clear, immediate explanation — not a confusing wait followed by a
   nonsensical result.

5. As a user, I can see a thumbnail of the actual image I uploaded
   alongside the analysis, so I have a visual reference for what's
   being described rather than taking the text on faith.

6. As a lay visitor unfamiliar with art/legal/financial jargon, I can
   hover over technical terms (e.g. "craquelure," "provenance,"
   "buyer's premium," "attributed to") and see a plain-language
   definition, without leaving the page or breaking my reading flow.

## Pages / views

- **Upload view**: file input (drag-and-drop + click-to-browse),
  optional fields (known title/artist/period/medium), variant selector
  (Auction House / Public Gallery), submit button.
- **Loading view**: shown while `POST /api/analyze` is in flight.
  Since the API is a single blocking request (no streaming, per the
  API spec's stated scope), this cannot show real live per-stage
  progress — but should still communicate that a multi-stage process is
  happening (e.g. a sequential-reveal animation of stage
  names/descriptions timed heuristically, not driven by real server
  events) rather than a single generic spinner with no context. Must
  clearly indicate this can take 60-90+ seconds (per observed pipeline
  timing in testing) so the user doesn't think the app has frozen.
- **Results view**: the core showcase surface — see "Results view
  layout" below.
- **Error view**: for `NotArtworkError` (422) and other failures —
  shown inline or as a distinct state, not a generic browser error
  page. `NotArtworkError` specifically should surface the actual
  `is_artwork_reasoning` message from the API.

## Results view layout

- **Header**: attribution (with hedge language preserved exactly as
  the API returns it — e.g. "Attributed to..." must render as-is, not
  be rephrased into unqualified confidence by the frontend), period/
  style, suggested title.
- **Visual analysis card**: composition, condition, authenticity notes.
- **Provenance card — both sub-agents shown, not collapsed**:
  Compliance Auditor and Provenance Historian each get their own
  visible section (risk level, reasoning/contextual notes). If their
  `risk_level` differs, this disagreement must be visually emphasized,
  not just present in the text — this is the single most important
  visual moment for demonstrating the architecture.
- **Valuation card — both sub-agents shown**: Conservative Appraiser
  and Bullish Specialist each get their own section (estimate,
  methodology, primary comp). The corridor (low-high range) should be
  visually represented (e.g. a simple range bar), and a wide-spread
  warning should be visually distinct, not buried in body text.
- **Evidence section**: the sampled evidence items from the API
  response, each rendered with a clickable, real `source_url` — every
  citable claim in this app must actually be clickable and verifiable
  by a judge, not just asserted.
- **Disclosures**: rendered prominently, not hidden in a footnote —
  these exist specifically because they're compliance-critical (see
  Curator's disclosure-floor design), and burying them in the UI would
  undermine the reason they're structurally guaranteed in the backend.
- **Exhibition narrative / wall label**: the actual Curator prose,
  clearly distinguishing the two (narrative = longer, wall label =
  short/display-ready).
- **Stage timing**: a simple visual (e.g. a small timeline/bar chart)
  showing the four stages' durations, with the concurrent stage 2
  visually indicated as parallel (e.g. two bars starting at the same
  point, not sequential) — this is the visual payoff for the
  concurrency work already validated in the backend.

## Acceptance criteria

- Both sub-agents at each dual-agent stage are always rendered as
  distinct, separately-labeled sections — never merged into a single
  paragraph or hidden behind a toggle/accordion that defaults closed.
- Hedge language from the API response renders verbatim — the frontend
  must not "clean up" or rephrase attribution/confidence language into
  something more confident-sounding.
- `NotArtworkError` responses render the actual reasoning message from
  the API, not a generic "something went wrong."
- All evidence `source_url`s render as real, clickable links opening in
  a new tab.
- The variant toggle actually re-triggers analysis with the new
  `variant_key` (or, if that would double API cost per demo run,
  clearly communicates to the user that switching variants requires
  re-analysis — flag this tradeoff back if it should be handled
  differently, e.g. running both variants once and caching both
  results client-side from a single backend call, which may require a
  small API change).
- Loading state clearly communicates expected wait time; does not look
  frozen or broken during the 60-90+ second wait.
- Disclosures are visually prominent (not default-collapsed, not
  small/faint text).
- A thumbnail of the actual uploaded image is visible in the results
  view, generated client-side from the file the user selected (no
  extra backend round-trip).
- Technical terms appearing anywhere in rendered prose (visual
  analysis, provenance reasoning, valuation methodology, exhibition
  copy) are detected against a maintained glossary and rendered with a
  hover tooltip showing a plain-language definition — applied
  consistently across all prose fields, not just a hardcoded subset of
  static UI labels, since the actual jargon appears in dynamically
  generated LLM text.

## Out of scope

- No user accounts/auth.
- No persistence — each analysis is a fresh request, nothing saved
  between sessions unless trivially easy to add with remaining time.
- No real-time streaming progress (matches the API's stated scope) —
  the loading view's stage reveal is a heuristic animation, not driven
  by live server events.