# Tasks: Provenance & Legal Agent

- [ ] 1. Define `RetrievedFact`, `EvidenceBundle`,
      `ComplianceAuditorOutput`, `ProvenanceHistorianOutput`,
      `TitleRiskMatrix` Pydantic models in
      `src/artgents/agents/provenance_legal.py`
- [ ] 2. Build `src/artgents/clients/parallel.py` — shared Parallel
      Search client (query in, parsed results with URLs out); no
      agent-specific query logic in the client itself
- [ ] 3. Build Wikidata SPARQL query logic (raw `httpx` POST, per
      `tech.md`) targeting ownership history (P127), collections
      (P195), and plunder/theft-related properties/events
- [ ] 4. Implement `gather_evidence()` — calls Wikidata, Met/AIC
      (reusing `MetClient`/AIC client), and Parallel Search once,
      assembles `EvidenceBundle` with every fact carrying a
      `source_url`
- [ ] 5. Implement `run_compliance_auditor()` — skeptic prompt/reasoning
      over the evidence bundle, flags gaps in known high-risk windows
      (1933-1945, pre-1970 UNESCO)
- [ ] 6. Implement `run_provenance_historian()` — advocate prompt/
      reasoning over the SAME evidence bundle, contextualizes gaps
      without dismissing genuine red flags
- [ ] 7. Implement `synthesize_title_risk()` as plain Python logic (not
      an LLM call) — sets `requires_human_review`, writes
      `synthesis_summary`, per design.md
- [ ] 8. Implement `assess_provenance()` — orchestrates
      `gather_evidence()` then `asyncio.gather()` over both sub-agents,
      then synthesis
- [ ] 9. Error handling: partial evidence on source failure (log ERROR,
      continue), typed error for Parallel Search credit exhaustion
- [ ] 10. Add logging via `logging_config.py`: retrieval latency/
       failures per source, sub-agent risk levels produced, whenever
       `requires_human_review` is set true — no `print()` calls
- [ ] 11. Unit tests: `EvidenceBundle` construction (mocked clients),
       both sub-agent outputs (mocked model responses),
       `synthesize_title_risk()` exhaustively over all risk_level
       combinations, partial-evidence-on-failure path
- [ ] 12. Integration test (manual/marked separately): real Wikidata
       query against a documented case, if a suitable public example
       exists
- [ ] 13. Wire `assess_provenance()` into `pipeline.py` as stage 2,
       consuming Visual Art Historian's `search_keys` output
- [ ] 14. Confirm `TitleRiskMatrix` matches Curator agent's expected
       input shape (once that agent's spec/interface exists)