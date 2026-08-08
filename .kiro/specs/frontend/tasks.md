# Tasks: Frontend

- [x] 0. (Backend prerequisite) DONE — pipeline/API now always return
      both Curator variants in one response; no `variant_key` request
      param exists.
- [ ] 1. Scaffold Vite + React + Tailwind project under `frontend/`
- [ ] 2. Define TypeScript types in `types/api.ts` mirroring the
      backend's `AnalyzeResponse` shape (check the actual Pydantic
      models rather than guessing field names/types)
- [ ] 3. Implement `api/client.ts` — `POST /api/analyze` wrapper
      (multipart form construction, error handling for 400/422/500)
- [ ] 4. Implement `UploadForm` — file input (drag-and-drop + browse),
      optional metadata fields, variant selector, submit
- [ ] 5. Implement `LoadingView` — heuristic timed stage reveal, clear
      "up to ~90 seconds" messaging
- [ ] 6. Implement `DualAgentCard` — reusable dual sub-agent display
      with disagreement highlighting, per design.md's prop shape
- [ ] 7. Implement `ResultsView` — header, visual analysis card, two
      `DualAgentCard` instances (provenance, valuation), evidence
      section, disclosures banner, exhibition narrative/wall label,
      stage timing chart
- [ ] 8. Implement `EvidenceList` — clickable source links, truncated
      display text
- [ ] 9. Implement `DisclosuresBanner` — prominent, non-collapsed
      rendering
- [ ] 10. Implement `StageTimingChart` — parallel visual for stage 2
- [ ] 11. Implement `VariantToggle` — client-side switch between the
       two already-fetched Curator outputs, no re-request
- [ ] 12. Implement `ErrorView` — distinguish `NotArtworkError` (422,
       show reasoning) from other failures (500, show failed stage)
- [ ] 13. Component tests: `DualAgentCard` disagreement-highlighting
       logic
- [ ] 14. Basic integration/smoke test: upload flow reaches
       `ResultsView` given a mocked API response
- [ ] 15. Manual end-to-end verification: real upload against the
       running backend, confirm hedge language renders verbatim,
       disclosures are prominent, evidence links work, timing chart
       shows stage 2 as parallel
- [ ] 16. Implement client-side image thumbnail: object URL generation
       on file select, display in `UploadForm` (preview) and
       `ResultsView` (persistent), proper cleanup on unmount/re-upload
- [ ] 17. Create `data/glossary.ts` — curated term/definition map
       covering art, provenance/legal, and financial jargon observed
       in real testing output
- [ ] 18. Implement `GlossaryText` component — case-insensitive
       whole-word term detection and hover-tooltip wrapping, custom
       styled (not native `title` attribute)
- [ ] 19. Apply `GlossaryText` to all prose fields across the results
       view (visual analysis notes, both sub-agents' reasoning at each
       dual-agent stage, methodology/primary_comp, corridor_summary,
       exhibition_narrative, wall_label) — not structured/numeric
       fields
- [ ] 20. Manual verification: confirm thumbnail displays correctly
       for a real upload, and hover tooltips appear for at least 3-4
       distinct glossary terms actually present in a real analysis
       result