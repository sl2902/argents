# Tasks: Demo Mode

- [ ] 1. (Sun) Select the real, already-verified golden result from
      tonight's testing and save it as
      frontend/src/data/golden-result.json, along with that same run's
      real job.logs array as frontend/src/data/golden-result-logs.json
- [ ] 2. Create scripts/generate_demo_narration.py - one-time offline
      TTS generation script per design.md
- [ ] 3. (Sun) Run the narration script once, review the six generated
      audio files for quality/tone before committing them
- [ ] 4. Build DemoCover.tsx - HTML/CSS/SVG only, matching app visual
      identity, Enter button routes into the explainer
- [ ] 5. Build PipelineExplainer.tsx - six-segment narrated walkthrough
      with synced captions, manual next/previous, honest runtime note
- [ ] 6. Build ResultsWalkthrough.tsx - reuses existing results-view
      components fed golden-result.json, guided spotlight/scroll,
      explicit disagreement-moment callouts
- [ ] 7. Wire routing (/demo entry point, separate from the live app's
      normal flow)
- [ ] 8. Manual verification per design.md's testing approach - full
      flow, audio playback, guided walkthrough, confirm no impact on
      the live app