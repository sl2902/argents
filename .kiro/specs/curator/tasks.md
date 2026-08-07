# Tasks: Curator Agent

- [ ] 1. Define `CuratorInput`, `CuratorOutput` Pydantic models in
      `src/artgents/agents/curator.py`
- [ ] 2. Implement `determine_disclosures()` as plain Python (not an
      LLM call) — the four-case disclosure logic per design.md, tested
      before any prompt-building happens
- [ ] 3. Implement variant-scoped prompt construction: auction_house
      includes valuation figures, public_gallery excludes them from
      narrative prose (disclosure floor still applies to both, via
      variant-appropriate phrasing)
- [ ] 4. Implement hedge-language preservation instructions in the
      prompt — attribution/provenance claims phrased as hedged upstream
      stay hedged in output prose
- [ ] 5. Implement `curate()` — loads config via
      `get_selectable_variant_config("curator", variant_key)`, computes
      disclosures, builds prompt, calls Vertex, parses into
      `CuratorOutput`
- [ ] 6. Add logging via `logging_config.py`: variant used, whether
      disclosure floor triggered, Vertex call latency/failures — no
      `print()` calls
- [ ] 7. Error handling: typed validation error for malformed/missing
      upstream input before any model call
- [ ] 8. Unit tests: `determine_disclosures()` exhaustive over all four
      `requires_human_review` combinations × both variants (8 cases)
- [ ] 9. Unit tests: variant-scoped content inclusion (mocked model
      responses) — auction_house includes dollar figures,
      public_gallery excludes them
- [ ] 10. Unit tests: hedge-language preservation, config-loader
       integration (variant_key=None falls back to YAML default,
       invalid variant_key raises)
- [ ] 11. Integration test (manual/marked separately): full run with
       real or realistic-fixture outputs from the other three agents
       against live Vertex AI
- [ ] 12. Wire `curate()` into `pipeline.py` as the final stage,
       consuming all three upstream agents' outputs
- [ ] 13. Confirm the full pipeline (Visual Art Historian ->
       Provenance/Legal + Financial Valuation -> Curator) runs
       end-to-end without manual intervention between stages