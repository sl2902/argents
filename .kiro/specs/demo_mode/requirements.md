# Requirements: Demo Mode

## Purpose

A guided, reliable, screen-recordable demo flow - cover screen ->
pipeline explainer -> results walkthrough - that does not depend on a
live pipeline run (60-90+ seconds, network-dependent, non-deterministic
model output) during recording or live presentation.

## Key design simplification

Unlike a dynamic narration system that describes a specific run's
specific findings, this demo's narration is generic and fixed - it
describes what each agent does, not what it found for any particular
artwork. That means all narration audio can be pre-generated once,
offline, via a one-time script, and shipped as static audio files - no
live TTS backend endpoint, no per-view API cost or latency. Similarly,
the results walkthrough uses one hand-picked, already-verified-good
cached analysis (a "golden result"), bundled as a static JSON asset and
rendered through the existing ResultsView component fed static data -
no new backend endpoint needed for this either.

## 1. Cover screen

- Pure HTML/CSS/SVG - no AI-generated imagery. Real HTML text for the
  app title/tagline, not baked into an image, so it's guaranteed
  legible (this avoids the text-rendering reliability problems AI
  image generation has for in-image text).
- Matches the app's existing visual identity (indigo/violet palette,
  existing icon/favicon design).
- **This is now the app's default landing at `/`** - not a separate
  `/demo`-only entry point. Anyone launching the app sees the cover
  first.
- An "Enter" button navigates into the MAIN live-upload app (the
  existing UploadForm/ResultsView flow) - not directly into the
  pipeline explainer.
- The main app gains a new button/link ("View Pipeline Demo" or
  similar) that navigates into the pipeline explainer directly
  (skipping the cover screen, since the user has already seen it).
- Cover is not re-shown on normal in-app navigation once past it -
  only on a fresh load of `/`.

## 2. Pipeline explainer

- ONE continuous page, not seven separately-navigated screens - an
  intro segment plus all six persona segments are laid out on one
  scrollable page, matching the pattern used in this project's earlier
  hackathon work where the pipeline explainer auto-played through the
  whole sequence rather than requiring the viewer to click through
  separate screens one at a time.
- The sequence is: intro (framing what's about to be shown) -> Visual
  Art Historian -> Compliance Auditor -> Provenance Historian ->
  Conservative Appraiser -> Bullish Specialist -> Curator. Seven
  segments total, six distinct voices (the intro shares Curator's
  voice as a narrator bookend - see "Voice assignment").
- Auto-play by default: narration audio plays in order, automatically
  advancing to the next segment's audio when the current one finishes
  (or after a reasonable fixed duration if that segment's audio is
  unavailable). As each segment becomes active, the page auto-scrolls
  to bring it into view and visually highlights it (similar treatment
  to the existing nested step-list's active/complete/pending states).
- A visible pause/play toggle lets the presenter pause the whole
  auto-play sequence at any point (e.g. to talk over a specific
  segment) and resume it. Manual skip forward/back to a specific
  segment is also available, for a presenter who wants to jump ahead
  or replay something, but the DEFAULT experience on load is
  auto-play through the whole thing without requiring any clicks.
- One narration segment per persona, each written and delivered in
  first person - the agent describing what it does, not a third-person
  description of it. The intro segment is the exception - it's a
  brief framing narration (not a specific agent describing itself)
  that sets up what the viewer is about to see, sharing Curator's
  voice per the bookend structure described in "Voice assignment."
- Given the project's actual point is the visible dual-agent debate,
  narration goes deeper than just the four top-level stages - six
  segments total: Visual Art Historian, Compliance Auditor, Provenance
  Historian, Conservative Appraiser, Bullish Specialist, Curator. Each
  paired sub-agent gets a genuinely distinct voice (per Gemini TTS
  voice assignment) so the contrast is audible, not just visible.
- Text captions displayed on screen in sync with the audio, so the
  explainer works even muted.
- Explicitly and honestly states the real observed runtime ("a full
  analysis typically takes 60-90+ seconds") as part of the framing -
  this is why the demo uses a pre-recorded/cached flow rather than a
  live run, and that reasoning should be stated on screen, not hidden.
- Pause/play toggle for the auto-play sequence, plus manual skip
  forward/back to jump to a specific persona - both available, but
  auto-play through the full sequence is the default on load, not
  something the presenter has to trigger manually per segment.
- Each segment also displays 1-3 REAL substep log lines from an actual
  captured pipeline run (the same run used for the golden result, so
  the explainer and the walkthrough tell one consistent story) -
  reusing the same nested step-list component already built for the
  live loading view, fed static data instead of live polling. This
  grounds each persona's first-person narration in something
  concrete and verifiable, rather than leaving it as unsupported
  character voiceover with nothing behind it. E.g. the Compliance
  Auditor segment shows its actual completion log line alongside its
  narration audio, not just the narration alone.

## 3. Results walkthrough

- **Demo-only compact display mode for evidence trail and exhibition
  copy.** This is a presentation choice for the walkthrough
  specifically, NOT a change to the live app's real results page — the
  live app must continue showing full, untruncated evidence
  descriptions and full curator narrative text, exactly as already
  built. `ResultsWalkthrough.tsx` passes a `compact` (or similarly
  named) prop into the shared results-view components, defaulting to
  `false` everywhere except this one usage, so a viewer following the
  auto-tour isn't expected to read the same volume of text a live user
  would have unlimited time to read at their own pace. Specifically:
  - Evidence trail items show a shorter excerpt (e.g. ~100 characters
    instead of the live app's ~300) with the full `source_url` still
    intact and clickable - the citation itself is never shortened,
    only the preview text.
  - Exhibition narrative (the longer Curator prose) shows a shorter
    excerpt with a clear "..." truncation indicator, not the full
    multi-paragraph text - the wall label (already short) can stay
    full-length.
  - This keeps the auto-tour's required dwell time per section shorter
    without needing the tour to move so fast a viewer can't actually
    process what's on screen, and without ever touching what the real,
    live app shows real users.
- Loads the golden cached result (static JSON asset) and renders it
  through the SAME `ResultsView` component used by the live app,
  showing ALL sections at once - visual analysis, both dual-agent
  cards (provenance and valuation), curator variant toggle, evidence
  trail, disclosures, AND the stage timing chart - exactly as a real
  live analysis result looks, not a trimmed or reordered subset. The
  full page is genuinely rendered and complete - not hidden behind
  steps - the same as a live analysis result.
- On top of that fully-rendered page, an AUTOMATIC guided tour plays by
  default: the page auto-scrolls through the sections in a sensible
  order (visual analysis -> provenance dual-agent cards -> valuation
  dual-agent cards -> curator -> evidence -> disclosures), visually
  highlighting/emphasizing whichever section is currently being
  narrated, without requiring the viewer to click "next" - matching the
  auto-playing pattern used in the pipeline explainer above. A
  pause/play toggle lets the presenter stop the auto-tour at any
  section and manually scroll/explore, since the full page is real and
  always fully present underneath the tour, not reconstructed per
  step.
- The primary callout (disagreement, or the cannot_determine framing
  described below) is presented as a prominent banner or highlighted
  panel at the top of the page, and the auto-tour should pause there
  slightly longer than other sections, since it's the most important
  moment - not as a gate the viewer must click through to reach the
  rest. The full page is visible immediately; the banner and the
  auto-tour's pacing draw attention to what matters most without
  hiding anything else.
  the callout draws attention to the most important part of it without
  gating access to the rest.
- The walkthrough's primary callout is determined by what the golden
  result ACTUALLY contains, not assumed in advance:
  - If the golden result includes genuine disagreement (differing
    risk_level values between the two sub-agents, or an unusually wide
    valuation spread with its own warning language), that disagreement
    is the primary callout.
  - If neither sub-agent's risk_level differs AND at least one is
    `"cannot_determine_insufficient_object_data"` (the actual case for
    the current golden result — both sub-agents independently reach
    this state), THAT becomes the primary callout instead, not a
    secondary note. This is a genuinely interesting thing to
    demonstrate in its own right: two independently-reasoning agents
    correctly recognizing the limits of available evidence, grounded
    in real AAM/AAMD museum provenance-review practice, rather than
    guessing. The walkthrough should frame this directly — e.g. "Watch
    what happens when the evidence genuinely isn't enough: instead of
    guessing, both agents say so, and explain why, using the same
    standard real museums use." — not undersell it as a fallback for
    "we couldn't find a disagreement to show you."
- If the golden result's evidence_scope is "artist_general" (no
  specific title known, so retrieval is scoped to the artist's body of
  work rather than this exact piece), the walkthrough must make that
  distinction explicit and impossible to misread — e.g. a caption
  like: "Notice what the agents actually say here: they found real,
  documented history tied to this artist's other work - but they're
  careful to state that it isn't evidence about this specific piece.
  That distinction is enforced by the system, not incidental - see
  evidence_scope in the underlying data." Without this callout, a
  viewer skimming quickly could misread a genuinely serious historical
  reference (e.g. Nazi-era plunder infrastructure appearing in the
  evidence) as a claim about the artwork being assessed, when the
  agents' own language is careful not to make that claim. For the
  current golden result specifically, this evidence_scope callout and
  the cannot_determine callout above are closely related and can be
  combined into one explanation: because evidence_scope is
  artist_general, the standard object-specific test cannot be applied,
  which is WHY both sub-agents correctly land on
  cannot_determine_insufficient_object_data rather than guessing.
- The full results page is rendered at once (same as a real live
  result), with the automatic guided tour and its pause/play toggle as
  described above - not step-gated manual next/previous. A "Back to
  explainer" or "Start over" link is also useful navigation.
- The artwork thumbnail (built earlier for the live app's ResultsView)
  must also display on this page. The live app's thumbnail component
  was built to read from an in-memory `File` object created during a
  real upload - this doesn't exist here, since ResultsWalkthrough loads
  a static JSON file with no accompanying image data. A static copy of
  the actual tested image (the same Met object used to produce the
  golden result) must be saved as a static asset and wired into the
  same thumbnail display, so this isn't a visible gap - the thumbnail
  component needs to accept either a live object URL (the existing
  upload-flow case) or a static image URL string (this case), not just
  the former.

## Voice assignment (Gemini TTS)

Six distinct voices, one per persona, chosen for genuine tonal
contrast - not the same voice reused with different text:
- Visual Art Historian - measured, analytical
- Compliance Auditor - firm, terse, skeptical
- Provenance Historian - warmer, more contextual/explanatory
- Conservative Appraiser - cautious, measured
- Bullish Specialist - more energetic/confident
- Curator - narrator-like, closing/synthesizing tone

## Acceptance criteria

- The full demo flow (cover -> explainer -> results walkthrough) works
  with zero live pipeline calls and zero live TTS calls - everything
  needed is either static HTML/CSS, pre-generated audio files, or a
  static JSON asset.
- Narration audio is generated once via an offline script (run by Sun,
  not part of the live app) and committed as static files - not
  regenerated on each page load.
- The golden result is a real, already-verified-good analysis (not a
  fabricated/hand-written fixture) - pulled from an actual prior
  pipeline run that was manually checked for quality (hedge language
  intact, dual-agent disagreement genuinely present, citations real).
- Cover screen uses no AI-generated imagery; all text is real HTML.
- Both the explainer and results walkthrough support manual
  advance/rewind, not forced auto-play only.

## Out of scope

- No dynamic/live narration of a specific real-time pipeline run -
  that would require the live TTS + dynamic-content architecture this
  design deliberately avoids for cost/reliability reasons.
- No editing of the existing live-upload app flow - this is an
  additive, separate demo entry point.