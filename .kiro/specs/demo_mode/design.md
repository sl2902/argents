# Design: Demo Mode

## Narration scripts (first person, one per persona)

These are the actual scripts - final content, not a placeholder. Each
is short enough to read comfortably in 15-25 seconds.

**Two versions of each script, used differently:**
- **Caption (plain text)** - displayed on screen, exactly as written
  below. This is what the frontend already shows and must NOT change.
- **TTS delivery (tagged text)** - what actually gets sent to the
  Gemini TTS API, with inline audio tags (e.g. `[firm]`, `[warm]`,
  `[short pause]`) that Gemini TTS interprets as delivery direction -
  confirmed real behavior against Google's own documentation
  (ai.google.dev/gemini-api/docs/speech-generation). The model speaks
  the actual words, not the tags themselves - tags shape HOW the line
  is delivered, they never appear as spoken text. Only the TTS
  generation script uses the tagged version; the frontend caption
  stays untagged.

There are SEVEN narration segments total, not six - an intro segment
plays first, before the six persona segments, framing what the viewer
is about to see. It shares Curator's voice (Kore) rather than
introducing a seventh distinct voice - this creates a bookend
structure: the same narrator-like voice opens the demo and later
closes it as Curator, while the four analytical sub-agent voices
(Aoede, Charon, Leda, Orus, Puck) stay reserved for their own segments
in between.

Intro:
Caption: "A gallery or auction house can spend hundreds of hours on a
single piece — tracing ownership, checking for red flags, defending a
price — before they'll commit to a claim. Artgents does that research
in 60 to 90 seconds — real calls to Vertex AI, Wikidata, the Met and
Art Institute of Chicago APIs, and Parallel Search. Because that's too
long to watch live, I'm walking through the architecture first, then
showing a completed run. It uses two independently-reasoning agents at
each contested step — not one averaged verdict."
TTS delivery: "[warm, confident] A gallery or auction house can spend
hundreds of hours on a single piece - tracing ownership, checking for
red flags, defending a price - before they'll commit to a claim.
[short pause] Artgents does that research in 60 to 90 seconds - real
calls to Vertex AI, Wikidata, the Met and Art Institute of Chicago
APIs, and Parallel Search. Because that's too long to watch live, I'm
walking through the architecture first, then showing a completed run.
[short pause] It uses two independently-reasoning agents at each
contested step - not one averaged verdict."

Visual Art Historian:
Caption: "I'm the first to look at the piece. I study the brushwork,
the materials, the composition - and I try to place it in art history.
If there's no visible signature, I won't pretend to certainty I don't
have. I'll tell you what style and period the evidence supports, and
I'll separate that from any guess at who painted it."
TTS delivery: "[measured] I'm the first to look at the piece. I study
the brushwork, the materials, the composition - and I try to place it
in art history. [thoughtful pause] If there's no visible signature, I
won't pretend to certainty I don't have. I'll tell you what style and
period the evidence supports, and I'll separate that from any guess at
who painted it."

Compliance Auditor:
Caption: "I'm the skeptic. I treat every gap in this artwork's
ownership history as a risk - especially if it falls during the Second
World War, or before international export rules existed in 1970. I
don't assume good faith. My job is to ask: what if something's wrong
here?"
TTS delivery: "[firm, terse] I'm the skeptic. I treat every gap in this
artwork's ownership history as a risk - especially if it falls during
the Second World War, or before international export rules existed in
1970. I don't assume good faith. [short pause] My job is to ask: what
if something's wrong here?"

Provenance Historian:
Caption: "I look at the same evidence my colleague does, but I ask a
different question: is this gap actually unusual? Most art from before
the twentieth century has incomplete records - that's normal, not
suspicious. I put the gap in context. We don't always agree, and that
disagreement is the point."
TTS delivery: "[warm, explaining] I look at the same evidence my
colleague does, but I ask a different question: is this gap actually
unusual? Most art from before the twentieth century has incomplete
records - that's normal, not suspicious. I put the gap in context.
[short pause] We don't always agree, and that disagreement is the
point."

Conservative Appraiser:
Caption: "I set the floor. I look at real comparable sales, and I ask:
what's the worst reasonable case? An attribution that isn't certain, a
market that's soft, a forced sale - I build all of that into a
defensible minimum."
TTS delivery: "[cautious, measured] I set the floor. I look at real
comparable sales, and I ask: what's the worst reasonable case? An
attribution that isn't certain, a market that's soft, a forced sale - I
build all of that into a defensible minimum."

Bullish Specialist:
Caption: "I set the ceiling. Same evidence as my colleague, different
question: what's this worth to the right buyer, under the right
conditions? Scarcity, momentum, a museum with real interest - I price
the upside they're not accounting for."
TTS delivery: "[confident, energetic] I set the ceiling. Same evidence
as my colleague, different question: what's this worth to the right
buyer, under the right conditions? Scarcity, momentum, a museum with
real interest - I price the upside they're not accounting for."

Curator:
Caption: "Once everyone else has spoken, I bring it together. I write
the exhibition copy - but I don't get to soften what the others found.
If there's a real disagreement or a real risk flagged upstream, it
shows up in what I write, every time, whether that makes a cleaner
story or not."
TTS delivery: "[measured, reflective] Once everyone else has spoken, I
bring it together. I write the exhibition copy - but I don't get to
soften what the others found. [short pause] If there's a real
disagreement or a real risk flagged upstream, it shows up in what I
write, every time, whether that makes a cleaner story or not."

## Voice assignment (Gemini TTS)

Using Gemini's prebuilt TTS voices - confirm current availability
against Vertex AI's TTS documentation before finalizing, since voice
names/availability can change:

| Persona | Voice | Rationale |
|---|---|---|
| Intro | Kore | Shared with Curator - narrator bookend, opens and closes the sequence |
| Visual Art Historian | Aoede | Clear, measured, analytical |
| Compliance Auditor | Charon | Firm, lower register, terse |
| Provenance Historian | Leda | Warmer, more explanatory |
| Conservative Appraiser | Orus | Cautious, measured |
| Bullish Specialist | Puck | Energetic, confident |
| Curator | Kore | Reserved, narrator/closing tone |

## Offline TTS generation - one-time script, not live infrastructure

scripts/generate_demo_narration.py - run once by Sun:
uv run python scripts/generate_demo_narration.py

Generates static audio files for the fixed demo narration scripts
using Gemini TTS via Vertex AI. NOT part of the live app - output
files are committed as static assets and served directly by the
frontend. Re-run only if a narration script's text changes.

The script defines a dict of persona -> narration text (the six
scripts above) and a dict of persona -> voice name (the table above).
For each persona: call Gemini TTS (reuse the existing Vertex client
setup/auth conventions from src/artgents/clients/vertex.py's
project/location config, but this script itself lives outside the
FastAPI app - it's a standalone one-time generation tool, not an
agent), get raw PCM, wrap in a WAV header (same approach as a prior
project - Python's wave module, 16-bit/24kHz/mono), save to
frontend/public/audio/{persona}.wav

## Golden result - selecting a real, already-verified example

The golden result must be a REAL analysis output already captured and
manually verified during this project's testing - not fabricated. Sun
selects the specific one to use (several strong candidates exist from
tonight's testing); the one with the most complete demo story is a run
that shows genuine dual-agent disagreement at the Provenance/Legal
stage (Compliance Auditor: red_flag, Provenance Historian: moderate,
tied to real Fuhrermuseum/Munich Central Collecting Point evidence)
alongside a real wide valuation spread - this demonstrates the core
architectural point (visible, evidence-grounded disagreement) more
clearly than a case where both sub-agents happened to converge.

Once selected, save the full AnalyzeResponse JSON as
frontend/src/data/golden-result.json - a static asset, not fetched
from any endpoint.

## Golden result manifest - provenance, not runtime tracking

Unlike a system that auto-tracks every completed job at runtime (not
needed here, since the golden result is hand-picked once, manually,
not accumulated from a live job stream), this is a small, static
provenance record - direct, checkable documentation that
golden-result.json is real captured output, not fabricated, per the
hackathon's own rule against passing off simulated data as real.

```json
// frontend/src/data/golden-result-manifest.json
{
  "source": "deployed Cloud Run backend (artgents-backend)",
  "captured_date": "2026-08-10",
  "job_id": "<the real job_id from that run>",
  "test_input": {
    "image": "Met object 459133 - The Adoration of the Magi (Follower of Giotto)",
    "known_artist": "Gentile da Fabriano"
  },
  "why_selected": "Genuine dual-agent disagreement at the Provenance/Legal stage (Compliance Auditor: red_flag, Provenance Historian: moderate), tied to real Wikidata evidence (Fuhrermuseum / Munich Central Collecting Point). Also demonstrates evidence_scope: artist_general handling - the retrieved evidence is about the artist's broader body of work, not the specific tested piece, and both sub-agents correctly say so."
}
```

Sun fills in the real values (actual job_id, actual date, actual test
input) when selecting the golden result in task 1 - this file
documents what was ACTUALLY run, not a template to guess at.

## Storage strategy for Cloud Run deployment - resolved, no action needed

Verified: every demo-mode asset (golden-result.json,
golden-result-logs.json, golden-result-manifest.json,
golden-result-image.jpg, the seven narration .wav files) is a purely
frontend-static asset - served by Vite in dev and Vercel in
production, either as static files under `frontend/public/` or bundled
directly into the JS build from `frontend/src/data/`. The FastAPI
backend never reads, serves, or touches any of them.

**Conclusion: no GCS integration is needed for demo-mode.** Cloud Run's
ephemeral local filesystem (the same limitation already documented for
the JOBS store and response cache) is irrelevant here, since the
backend never touches these files at all. Vercel's static hosting
already solves persistence for these assets permanently and correctly
- adding a GCS storage abstraction (the pattern used elsewhere in this
project's broader work, for artifacts a backend genuinely needs to
read/write at runtime) would be unnecessary infrastructure for a set
of fixed, authored-once files with zero backend involvement.

This conclusion applies specifically to demo-mode's current design. If
a future change ever routes any of these assets through a backend API
endpoint instead of serving them directly from the frontend, that
would reintroduce the need to reconsider this - but as designed today,
this is resolved and does not need revisiting.

## Frontend structure

frontend/src/
  pages/
    DemoCover.tsx          - HTML/CSS/SVG cover screen
    PipelineExplainer.tsx  - 6-segment narrated walkthrough
    ResultsWalkthrough.tsx - guided tour of golden-result.json
  data/
    golden-result.json     - static, real, pre-verified example
    golden-result-logs.json - the real job.logs array from that same
                               run, used to show real substeps per
                               narration segment
    golden-result-manifest.json - provenance record for the golden
                               result (see below)
public/
  audio/
    intro.wav
    visual_art_historian.wav
    compliance_auditor.wav
    provenance_historian.wav
    conservative_appraiser.wav
    bullish_specialist.wav
    curator.wav
  golden-result-image.jpg - static copy of the actual tested image
                             (the same Met object used to produce
                             golden-result.json), so ResultsWalkthrough
                             has something to display in the thumbnail
                             slot - the live app's thumbnail component
                             reads from an in-memory File object that
                             doesn't exist in this static context, so
                             the thumbnail component needs to accept a
                             plain image URL as an alternative source

ResultsWalkthrough.tsx renders the SAME `ResultsView` component used by
the live app - feeding it golden-result.json instead of a live API
response - with EVERY section genuinely present in the DOM at once:
visual analysis, both dual-agent cards, curator variant toggle,
evidence trail, disclosures, AND the stage timing chart. Do not build a
second, trimmed, or reordered version of the results UI - the
underlying page is the real one, and this doesn't change: no section
is removed or reordered.

**Compact mode is a display-density toggle, not a trimmed version.**
`EvidenceList` and the exhibition-copy display components accept a
`compact?: boolean` prop (default `false`, so the live app's existing
behavior is completely unaffected). When `true` (set only by
ResultsWalkthrough), evidence item descriptions truncate to ~100
characters instead of the existing ~300, and exhibition narrative
shows a shortened excerpt with a "..." indicator instead of the full
text - `source_url` links are never shortened or removed in either
mode. This is purely about how much text is visually shown at once
during an automated, timed tour, not a change to what data exists or
what a real user browsing at their own pace would see on the live
results page.

Layered on top: an auto-tour controller (a simple ordered list of
section refs + a timer/interval) auto-scrolls the page to each
section in sequence and applies a highlight/emphasis class to the
current section (dim or reduce opacity on the rest) - the same visual
treatment originally planned for the removed step-based version, just
driven by an automatic timer/sequence instead of manual next/previous
clicks. A pause/play toggle stops/resumes the auto-tour; while paused,
the full page remains fully present and scrollable/explorable
manually, since nothing was ever hidden - the tour is a camera, not a
gate.

Tour ordering: banner/primary callout (paused on longer than other
steps, since it's the most important content) -> visual analysis ->
provenance dual-agent cards -> valuation dual-agent cards -> curator ->
evidence trail -> disclosures.

Primary banner content is determined by the actual golden-result.json
content, not assumed:
- If risk_level genuinely differs between the two sub-agents (or the
  valuation corridor carries wide-spread warning language), that
  disagreement is the primary banner content.
- OTHERWISE, if either sub-agent's risk_level is
  "cannot_determine_insufficient_object_data" (the actual state of the
  current golden result - BOTH sub-agents independently reach this
  state), that becomes the primary banner content instead, framed as a
  genuine capability, not a fallback: e.g. "Watch what happens when
  the evidence genuinely isn't enough: instead of guessing, both
  agents say so, and explain why - grounded in the same standard real
  museums use (AAM/AAMD guidelines)." This should read as
  demonstrating good judgment, not as "we couldn't find a
  disagreement, here's a consolation moment."

For the current golden result specifically, the evidence_scope
("artist_general") explanation and the cannot_determine explanation
are the same underlying story, not two separate callouts: because
evidence_scope is artist_general (no way to tie retrieved evidence -
including the real Fuhrermuseum/Munich Central Collecting Point
history for a DIFFERENT specific work by this artist - to the actual
piece being assessed), both sub-agents correctly cannot apply the
standard object-specific risk test, hence
cannot_determine_insufficient_object_data. One combined callout should
walk through this chain clearly: evidence found -> why it can't be
tied to this piece -> why that means risk_level can't be determined ->
why that's the honest answer, not a gap in the system.

PipelineExplainer.tsx lays out all six persona segments on ONE
continuous scrollable page (not six separately-navigated screens) and
auto-plays through them by default: each persona's narration audio
plays in sequence, auto-advancing to the next persona's audio when the
current one finishes (or after a reasonable fixed duration if that
segment's audio file is unavailable, per the graceful-fallback
behavior already built). As each persona becomes active, the page
auto-scrolls to bring that segment into view and applies a highlight/
emphasis treatment, similar to the nested step-list's active/complete/
pending visual states.

A visible pause/play toggle stops/resumes the whole auto-play
sequence at any point. Manual skip forward/back to a specific persona
is also available for a presenter who wants to jump ahead or replay a
segment - but auto-play through the full sequence is the default
experience on page load, requiring no clicks to start. A visible,
honest note about real pipeline runtime (60-90+ seconds) frames why
this demo doesn't run live.

Each segment also renders the real substep log entries (ProgressEntry
objects, per the pipeline/API specs) tied to that persona, pulled from
the same real pipeline run used for the golden result - stored
alongside golden-result.json as a second static asset,
golden-result-logs.json (the full job.logs array from that actual run).
Reuses the existing nested/indented step-list rendering component
already built for the live loading view (see .kiro/specs/frontend's
"Loading view - grouped/indented step display" section) rather than
building new UI, just fed this static log array instead of live
polling data. Since the six personas don't map 1:1 onto the four
stage_key values (compliance_auditor and provenance_historian both
fall under "concurrent_research", as do conservative_appraiser and
bullish_specialist), each persona segment shows the subset of that
stage's real log lines relevant to it - e.g. the Compliance Auditor
segment shows "Provenance sub-agents completed their assessments" and
any Wikidata/Met/AIC/Parallel retrieval lines that fed into it, not
every concurrent_research log line indiscriminately.

## Routing

Reversed from an earlier design (cover as a `/demo`-only entry point):

- `/` renders the cover screen by default - this is now the app's
  actual landing page, not a separate demo-only route.
- Cover's "Enter" button navigates to the main live-upload app (its
  existing route, e.g. `/app` or wherever `App.tsx` is now mounted -
  confirm the actual current route when implementing, since adding the
  cover as the new `/` requires moving the live app off that path).
- The main live-upload app gains a new button/link ("View Pipeline
  Demo") that navigates directly to the pipeline explainer (e.g.
  `/demo/explainer`), skipping the cover screen since the user has
  already seen it in this session.
- `PipelineExplainer` completing (or a link within it) navigates to
  `ResultsWalkthrough` (e.g. `/demo/results`).
- The cover screen is NOT re-shown by navigating within the app after
  first load - only a fresh load of `/` shows it again.

## Testing approach

Primarily manual verification given this is a presentation/demo
artifact, not core application logic:
- Confirm the cover screen renders correctly and the Enter button
  navigates into the explainer.
- Confirm all six audio files play correctly with synced captions, and
  next/previous controls work.
- Confirm the results walkthrough correctly renders the golden result
  through the real, existing components, with working guided
  spotlight/scroll and disagreement-moment callouts.
- Confirm none of this touches or breaks the live-upload app flow.