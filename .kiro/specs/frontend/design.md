# Design: Frontend

## Tech stack

React + Vite, matching the established pattern across prior projects
(Codex Anatomy, Oikos Ledger, BlastRadius, Patchnote). Tailwind for
styling. No additional framework assumptions beyond what's already
implied by `frontend/` in the repo layout.

## Variant toggle

Per the pipeline/API's "Reuse over re-run" design (see
`.kiro/steering/structure.md`), `POST /api/analyze` always returns
BOTH Curator variants (`curator_auction_house`, `curator_public_gallery`)
in one response — there is no `variant_key` request parameter and no
second request needed. The frontend toggles between the two client-side
with zero additional network calls.

## Page structure

```
src/
├── main.tsx
├── App.tsx
├── components/
│   ├── UploadForm.tsx
│   ├── LoadingView.tsx
│   ├── ResultsView.tsx
│   ├── DualAgentCard.tsx       # reusable: renders two sub-agent
│   │                            # views side by side, used for both
│   │                            # provenance and valuation
│   ├── EvidenceList.tsx
│   ├── DisclosuresBanner.tsx
│   ├── StageTimingChart.tsx
│   ├── VariantToggle.tsx
│   └── ErrorView.tsx
├── api/
│   └── client.ts                # fetch wrapper for POST /api/analyze
└── types/
    └── api.ts                    # TypeScript types mirroring
                                    # AnalyzeResponse from the backend
```

## `DualAgentCard` — the core showcase component

One reusable component, used twice (provenance, valuation), since both
follow the same visual pattern: two sub-agent views side by side (or
stacked on mobile), with a visually distinct "disagreement" state when
risk levels/estimates diverge significantly.

```tsx
interface DualAgentCardProps {
  title: string;  // "Provenance Assessment" | "Financial Valuation"
  leftLabel: string;   // "Compliance Auditor" | "Conservative Appraiser"
  leftContent: React.ReactNode;
  leftVerdict: string; // risk_level or formatted estimate
  rightLabel: string;
  rightContent: React.ReactNode;
  rightVerdict: string;
  disagreement: boolean;  // drives visual emphasis (e.g. a warning
                            // border/badge) when true
  synthesisSummary: string;
}
```

## Loading view — grouped/indented step display

`job.logs` is now a list of `{stage_key, message}` entries (see the
API spec's "Job store — structured progress entries"). Render this as
FOUR parent groups, one per canonical `stage_key`
(`"start"`, `"visual_analysis"`, `"concurrent_research"`, `"curator"`),
each showing its own top-level label (matching the original 4-step
labels) with any substep entries for that stage rendered nested/
indented beneath it, in the order received. Group by `stage_key`
directly — do not infer grouping from message text content, which
would be fragile against wording changes.

A parent stage is `complete` once at least one entry for the NEXT
stage_key has arrived (i.e. the pipeline has moved on); the parent
whose stage_key matches the most recent entry is `active`; stages with
no entries yet are `pending`. Within an active parent, all its received
substep entries render as completed/checked, indented under the parent,
in arrival order.

## Loading view — real polling-driven step display

Per the async job pattern (see `.kiro/specs/api/design.md`'s "Job
store"), the loading view polls `GET /api/status/{job_id}` and
receives `job.logs` — a growing list of real, completed progress
messages (not a single "current" message that replaces the previous
one). The UI must render this as an ACCUMULATING sequence — each
completed step stays visible with a completed/checked state, the most
recent entry is the current/active step, and future (not-yet-reached)
steps are shown as pending — preserving the connected-steps visual
pattern (arrows/connectors between steps, highlighted current step)
from the original design, just now driven by real data instead of a
heuristic timer.

**This was a real regression to fix, not a new design**: an earlier
implementation rendered only the latest `job.logs` entry, which visibly
overwrote the previous step instead of accumulating — losing the
step-by-step progression the original heuristic version had. The fix
is to always render the full `job.logs` array received so far, mapped
to step states (`complete` for all but the last entry, `active` for
the last entry, `pending` for any expected-but-not-yet-seen steps),
not just display the single latest string.

If the pipeline reports fewer or more progress messages than
originally assumed (currently: "Analyzing artwork...", "Researching
provenance and estimating valuation...", "Writing exhibition
copy...", "Complete." — four messages, not three), the step display
should size itself to however many entries are actually present in
`job.logs`, not a hardcoded step count.

## Hedge language and disclosure rendering — no rephrasing

The frontend renders API text fields verbatim — no client-side
rewriting, summarizing, or "cleaning up" of attribution/confidence
language. This preserves the hedge-language guarantees already built
and tested at the Curator/Visual-Art-Historian level; a frontend that
paraphrases "Attributed to X" into "By X" for cleaner-looking copy
would silently undo that work.

`DisclosuresBanner` renders prominently (e.g. a visually distinct
banner above the fold in the results view, not a collapsed accordion)
whenever `disclosures` is non-empty.

## Evidence rendering

`EvidenceList` renders each sampled evidence item's truncated
description plus its `source_url` as a real `<a target="_blank">`
link — every citable claim must be independently verifiable by
clicking through, consistent with the "every claim needs a real
source_url" principle enforced throughout the backend.

## Stage timing visualization

`StageTimingChart`: a simple horizontal bar/timeline using the API's
`timings` object. Visual requirement: stage 2 (Provenance/Legal +
Financial Valuation) renders as two bars starting at the same
horizontal position (parallel), not sequential after stage 1 — this is
the visual payoff for the concurrency already verified in backend
testing. A basic CSS/flexbox layout is sufficient; no charting library
required unless one is already a natural fit.

## Error handling

`ErrorView` distinguishes `NotArtworkError` (422 — show the actual
`is_artwork_reasoning` message, framed as "this doesn't look like an
artwork" rather than a generic error) from other failures (500 — show
which stage failed, per the API's error shape, without a raw stack
trace).

## Image thumbnail

Held entirely client-side — no backend change needed, since the
browser already has the `File` object the user selected. On file
select, generate an object URL (`URL.createObjectURL(file)`) and store
it in component state alongside the upload. Display it in both
`UploadForm` (preview before submit) and `ResultsView` (persistent
reference alongside the analysis) — same object URL, no need to
re-read the file. Revoke the object URL on unmount/new upload to avoid
a memory leak.

## Glossary tooltips

```
src/
├── data/
│   └── glossary.ts   # term -> plain-language definition map
├── components/
│   └── GlossaryText.tsx   # wraps a block of prose, detects and
│                            # highlights known terms with a hover
│                            # tooltip
```

`glossary.ts` is a curated `Record<string, string>` covering terms
actually observed across this project's testing — art/technique terms
(craquelure, sgraffito, punchwork, gesso, tempera, gilding, oilstick),
provenance/legal terms (provenance, attribution, restitution,
forfeiture, UNESCO Convention, red flag), and financial/auction terms
(hammer price, buyer's premium, illiquidity discount, comparable
sale/comp, corridor, floor/ceiling estimate). Extend as new terms are
noticed in real output during testing — this is a living list, not a
one-time fixed set.

`GlossaryText` takes a block of text (e.g. `composition_analysis`,
`exhibition_narrative`, any prose field from the API response), does a
case-insensitive whole-word scan against `glossary.ts`'s keys, and
wraps each match in a styled `<span>` with a hover tooltip showing the
definition — implemented as a lightweight custom tooltip (CSS
`:hover` + positioned element, or a small headless tooltip primitive),
not the native browser `title` attribute, which is slow to appear and
not visually consistent with the rest of the UI.

Apply `GlossaryText` everywhere prose from the API is rendered:
composition/condition/authenticity notes, both sub-agents' reasoning
text at each dual-agent stage, `methodology`/`primary_comp`,
`corridor_summary`, `exhibition_narrative`, `wall_label`. Do NOT apply
it to structured/numeric fields (estimates, risk levels, timings) —
only free-text prose.

## Testing approach

Given hackathon time constraints, prioritize:
- Component-level tests for `DualAgentCard`'s disagreement-highlighting
  logic (the single most important visual behavior)
- A basic integration/smoke test that the upload flow reaches
  `ResultsView` given a mocked API response
- Manual visual verification of the rest, given time pressure —
  flag if you want more automated coverage and we can revisit
  priorities