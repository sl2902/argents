# Tasks: API Layer

- [ ] 1. Create `src/artgents/api/` package (`__init__.py`, `app.py`,
      `routes.py`, `response_models.py`)
- [ ] 2. Extend `PipelineResult` (or wrap it) in `pipeline.py` to
      capture stage-boundary timestamps as structured data, not just
      log lines — small addition, reuse existing stage-transition
      logging points
- [ ] 3. Define `AnalyzeResponse` and nested response models in
      `response_models.py`, reusing existing agent Pydantic models for
      sub-agent outputs rather than redefining schema
- [ ] 4. Implement evidence sampling/truncation logic (first N entries,
      ~300 char truncation, full counts preserved) — confirm this
      never mutates the underlying `PipelineResult`
- [ ] 5. Implement `POST /api/analyze`: parse multipart upload(s) +
      optional form fields, build `PipelineInput`, call
      `run_pipeline()`, shape into `AnalyzeResponse`
- [ ] 6. Implement `GET /api/health` — trivial, no agent/model calls
- [ ] 7. Implement typed-exception → HTTP status handlers, each
      identifying the failing stage in the response body
- [ ] 8. Configure CORS with a permissive dev default; comment noting
      it should be tightened before final submission
- [ ] 9. Unit tests: response model construction from a mocked
      `PipelineResult` (truncation, sampling, timing correctness)
- [ ] 10. Unit tests: error handlers map each typed exception to
       correct status + stage field
- [ ] 11. Integration test (manual/marked separately): real
       `POST /api/analyze` via FastAPI test client against the real
       pipeline with an actual image
- [ ] 12. Confirm `uv run uvicorn artgents.api.app:app` (or equivalent)
       starts the server and `GET /api/health` responds correctly