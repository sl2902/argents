# Tasks: Pipeline Orchestration

- [ ] 1. Define `PipelineInput`, `PipelineResult` Pydantic models in
      `src/artgents/pipeline.py`
- [ ] 2. Implement `run_pipeline()` — stage 1 (Visual Art Historian),
      per design.md
- [ ] 3. Implement stage 2 — `assess_provenance()` and
      `assess_valuation()` run via `asyncio.gather`, both consuming
      `visual_analysis.search_keys`
- [ ] 4. Implement stage 3 — `curate()` consuming all three prior
      outputs plus `input.variant_key`
- [ ] 5. Assemble and return `PipelineResult` with all four agents'
      outputs accessible, not just the final `CuratorOutput`
- [ ] 6. Add stage-transition logging via `logging_config.py` — no
      `print()` calls; log level should let a full run's timeline be
      reconstructed from logs alone
- [ ] 7. Confirm error propagation: no try/except suppression inside
      `run_pipeline()` — exceptions from any stage surface naturally
- [ ] 8. Unit tests: mocked agent functions — correct call order,
      verified concurrency of stage 2 (timing-based or in-flight
      assertion), correct `PipelineResult` aggregation, exception
      propagation from each stage
- [ ] 9. Integration test (manual/marked separately): one full real run
      with an actual image, asserting a valid `PipelineResult`
- [ ] 10. Run the integration test and confirm the full four-agent
       chain executes with no manual intervention between stages —
       this closes the acceptance bar originally stated in Curator's
       own tasks.md (task 13)