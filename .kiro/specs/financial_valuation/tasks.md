# Tasks: Financial Valuation Agent

- [ ] 1. Define `ComparableSale`, `ComparableSalesEvidence`,
      `ConservativeAppraiserOutput`, `BullishSpecialistOutput`,
      `ValuationCorridor`, `FinancialValuationResult` Pydantic models in
      `src/artgents/agents/financial_valuation.py`
- [ ] 2. Implement `gather_comps()`: Parallel Search (reusing existing
      hardened query-filtering/relevance logic from Provenance/Legal)
      + Wikidata sale-price query (reusing `WikidataClient` with its
      existing default `LIMIT`, targeting P2296/P1088) — one pass,
      assembles `ComparableSalesEvidence`
- [ ] 3. Implement evidence-scoping logic (`evidence_scope`,
      `source_entity_id` per comp) — mirror the exact logic from
      Provenance/Legal's `gather_evidence()`, including the "Unknown"/
      no-title fallback behavior (skip artist-driven Wikidata query
      when no specific artist name is available, same as
      `_retrieve_wikidata`'s existing guard)
- [ ] 4. Implement `run_conservative_appraiser()` — floor-value
      reasoning over the evidence bundle, optionally factoring in
      `title_risk` if provided; artist_general-mode framing per
      requirements.md
- [ ] 5. Implement `run_bullish_specialist()` — ceiling-value reasoning
      over the SAME evidence bundle; artist_general-mode framing
- [ ] 6. Implement `synthesize_valuation()` as plain Python logic (not
      an LLM call) — sets `requires_human_review`, writes
      `corridor_summary` including wide-spread flagging, per design.md
- [ ] 7. Implement `assess_valuation()` — orchestrates `gather_comps()`
      then `asyncio.gather()` over both sub-agents, then synthesis
- [ ] 8. Error handling: partial evidence on source failure (log ERROR,
      continue), malformed `source_url` on a comp → drop + increment
      `rejected_fact_count` + log WARNING (reuse Provenance/Legal
      pattern)
- [ ] 9. Add logging via `logging_config.py`: retrieval latency/
      failures per source, which estimates each sub-agent produced,
      whenever `requires_human_review` is set true — no `print()` calls
- [ ] 10. Wire config loading via
       `config_loader.get_dual_agent_config("financial_valuation")` —
       do not hardcode temperature/max_output_tokens/voice framing
- [ ] 11. Unit tests: `ComparableSalesEvidence` construction (mocked
       clients) including evidence_scope logic mirroring
       Provenance/Legal's test cases, both sub-agent outputs (mocked
       model responses), `synthesize_valuation()` exhaustively over
       confidence/scope combinations, partial-evidence-on-failure path,
       malformed-source_url rejection path
- [ ] 12. Integration test (manual/marked separately): real artist/
       title with findable public sale coverage, run against live
       Parallel Search + Wikidata
- [ ] 13. Wire `assess_valuation()` into `pipeline.py` — consumes
       Visual Art Historian's `search_keys`, optionally
       Provenance/Legal's `TitleRiskMatrix` if pipeline ordering makes
       it available
- [ ] 14. Confirm `FinancialValuationResult` matches Curator agent's
       expected input shape (once that agent's spec/interface exists)