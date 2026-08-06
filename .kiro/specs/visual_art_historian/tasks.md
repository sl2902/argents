# Tasks: Visual Art Historian Agent

- [ ] 1. Define `VisualAnalysisInput`, `ProvenanceSearchKeys`, and
      `VisualAnalysisOutput` Pydantic models in
      `src/artgents/agents/art_historian.py`
- [ ] 2. Implement/extend `src/artgents/clients/vertex.py` with a
      multimodal call helper (image + text → structured JSON) if it
      doesn't already exist from another agent's work
- [ ] 3. Write two prompt branches: blind discovery (no metadata) vs.
      verification (metadata supplied, check consistency and flag
      anomalies) — plus the attribution-phrasing constraint
      ("Attributed to..." unless a legible signature is visible)
- [ ] 4. Implement `analyze_artwork()` — input validation, model call,
      response parsing into `VisualAnalysisOutput`
- [ ] 5. Handle invalid/corrupt image input with a clear pre-call
      validation error
- [ ] 6. Add logging via `logging_config.py`: prompt branch taken, Vertex
      call latency/failures (ERROR on failure), low-confidence or
      anomaly-flagged output (WARNING) — no `print()` calls
- [ ] 7. Unit tests: schema validation, blind-discovery path,
      verification path (both consistent and anomaly-flagged cases),
      invalid image rejection (mocked Vertex client)
- [ ] 8. Integration test (manual/marked separately): one real public
      domain image from Met Open Access, run against live Vertex AI
- [ ] 9. Wire `analyze_artwork()` into `pipeline.py` as the first stage
      of the run — confirm `search_keys` is passed to Provenance/Legal
      agent BEFORE Curator agent runs (sequential, not fan-out)
- [ ] 10. Confirm `search_keys` matches Provenance/Legal agent's expected
       input shape (once that agent's spec/interface exists)
- [ ] 11. Confirm `composition_analysis`/`condition_notes`/
       `stylistic_authenticity_notes` match Curator agent's expected
       input shape, alongside Provenance/Legal's own output (once that
       agent's spec/interface exists)