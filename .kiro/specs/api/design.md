# Design: API Layer

## Architecture

```
POST /api/analyze (multipart)
        │
        ▼
┌────────────────────────────┐
│ Creates job_id, stores      │
│ initial status in JOBS,     │
│ starts run_pipeline() as a  │
│ background task with an     │
│ on_progress callback that   │
│ appends to JOBS[job_id]     │
│ .logs, returns job_id       │
│ immediately (does NOT block)│
└────────────────────────────┘
        │
        ▼
  {"job_id": "..."}


GET /api/status/{job_id}  (polled repeatedly by frontend)
        │
        ▼
┌────────────────────────────┐
│ Reads JOBS[job_id]:          │
│  - status                    │
│  - logs (real progress)      │
│  - result (once complete,    │
│    shaped into                │
│    AnalyzeResponse)           │
│  - error (if failed)          │
└────────────────────────────┘
```

## Job store — structured progress entries

`Job.logs` holds structured entries, not plain strings, so the
frontend can group substeps under their correct parent stage reliably:

```python
class ProgressEntry(BaseModel):
    stage_key: str  # "start" | "visual_analysis" |
                      # "concurrent_research" | "curator"
    message: str

@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.PENDING
    logs: list[ProgressEntry] = field(default_factory=list)
    result: AnalyzeResponse | None = None
    error: str | None = None
    failed_stage: str | None = None
```

`execute_job()`'s `on_progress` callback now takes `(stage_key,
message)` matching `run_pipeline()`'s updated signature, and appends a
`ProgressEntry` rather than a bare string.

## Job store — actual bug found in implementation

The implemented `Job` dataclass has `progress: str` (single string,
overwritten on every `on_progress()` call) instead of the intended
`logs: list[str]` (accumulating). This is why the frontend only ever
showed the single latest step — there was nothing to accumulate,
`job.progress` structurally can't hold history. This must be fixed at
the data model level: `Job.progress` should become `Job.logs:
list[str] = field(default_factory=list)`, and `on_progress()` should
append (`job.logs.append(msg)`) rather than assign. `GET
/api/status/{job_id}`'s response shape and the frontend's expected
field name both need to match this corrected field.

## Job store

```python
# src/artgents/api/jobs.py

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"

class Job(BaseModel):
    status: JobStatus
    logs: list[str] = []
    result: AnalyzeResponse | None = None
    error: str | None = None
    failed_stage: str | None = None

JOBS: dict[str, Job] = {}  # in-memory — single-instance only,
                            # see requirements.md "Job store" section
                            # for the explicit scope decision

def create_job() -> str:
    job_id = str(uuid.uuid4())
    JOBS[job_id] = Job(status=JobStatus.QUEUED)
    return job_id

async def execute_job(job_id: str, pipeline_input: PipelineInput) -> None:
    JOBS[job_id].status = JobStatus.RUNNING

    def on_progress(message: str) -> None:
        JOBS[job_id].logs.append(message)

    try:
        result = await run_pipeline(pipeline_input, on_progress=on_progress)
        JOBS[job_id].result = shape_analyze_response(result)  # existing
                                                                 # response-shaping logic
        JOBS[job_id].status = JobStatus.COMPLETE
    except NotArtworkError as e:
        JOBS[job_id].status = JobStatus.FAILED
        JOBS[job_id].error = str(e)
        JOBS[job_id].failed_stage = "visual_art_historian"
    except Exception as e:
        JOBS[job_id].status = JobStatus.FAILED
        JOBS[job_id].error = str(e)
        JOBS[job_id].failed_stage = "unknown"  # or map specific typed
                                                  # exceptions to their
                                                  # stage, same mapping
                                                  # as the previous
                                                  # synchronous handlers
```

## Route handlers

```python
@app.post("/api/analyze")
async def analyze(files: list[UploadFile] = File(...), ...) -> dict:
    # existing multipart parsing / base64 encoding logic unchanged
    pipeline_input = PipelineInput(images=[...], ...)
    job_id = create_job()
    asyncio.create_task(execute_job(job_id, pipeline_input))
    return {"job_id": job_id}

@app.get("/api/status/{job_id}")
async def get_status(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
```

Reuse `asyncio.create_task` (simple, no extra dependency) rather than
FastAPI's `BackgroundTasks` if `analyze()` needs to return before the
task is guaranteed scheduled — check which fits the actual FastAPI
version/patterns already in use in the codebase; either is acceptable,
prefer whichever is more consistent with existing code.

## File layout

```
src/artgents/
├── api/
│   ├── __init__.py
│   ├── app.py              # FastAPI app instance, CORS config
│   ├── routes.py           # /api/analyze, /api/health
│   └── response_models.py  # AnalyzeResponse and nested shapes
```

## Response models

```python
# src/artgents/api/response_models.py

class SubAgentTimingBreakdown(BaseModel):
    stage_name: str
    duration_ms: int

class StageTimings(BaseModel):
    visual_analysis_ms: int
    stage_2_wall_clock_ms: int  # actual elapsed time for stage 2
                                  # (concurrent) — the number that
                                  # demonstrates parallelism
    provenance_ms: int          # provenance/legal's own duration
    valuation_ms: int           # financial valuation's own duration
    curator_ms: int
    total_ms: int

class EvidenceItemDisplay(BaseModel):
    description: str  # truncated for display
    source_url: str
    source_type: str

class CuratorOutputDisplay(BaseModel):
    exhibition_narrative: str
    wall_label: str
    suggested_title: str
    disclosures: list[str]

class AnalyzeResponse(BaseModel):
    # Visual analysis
    attribution: str
    period_style: str
    composition_analysis: str
    condition_notes: str
    stylistic_authenticity_notes: str

    # Provenance — both sub-agents, not just synthesis
    compliance_auditor: ComplianceAuditorOutput
    provenance_historian: ProvenanceHistorianOutput
    provenance_synthesis_summary: str
    provenance_requires_human_review: bool

    # Valuation — both sub-agents
    conservative_appraiser: ConservativeAppraiserOutput
    bullish_specialist: BullishSpecialistOutput
    valuation_corridor: ValuationCorridor
    corridor_summary: str
    valuation_requires_human_review: bool

    # Curator — BOTH variants, no request-time selection needed
    curator_auction_house: CuratorOutputDisplay
    curator_public_gallery: CuratorOutputDisplay

    # Evidence sample
    provenance_evidence_sample: list[EvidenceItemDisplay]
    valuation_evidence_sample: list[EvidenceItemDisplay]
    total_provenance_facts: int  # full count, even if sample is smaller
    total_valuation_comps: int

    # Timing
    timings: StageTimings
```

Reuses the existing Pydantic sub-models (`ComplianceAuditorOutput`,
`ProvenanceHistorianOutput`, etc.) directly from their agent modules
rather than redefining them — no duplication of schema.

## Timing capture

`run_pipeline()` itself (per the pipeline spec) already logs
stage-transition timestamps but doesn't currently return them as data.
Extend `PipelineResult` (or wrap it) to also capture timestamps at each
stage boundary, so the API layer can compute `StageTimings` without
re-deriving it from log parsing. This is a small addition to
`pipeline.py`, not a new concept — the logging already proves the
timing exists, this just captures it as structured data too.

## Evidence sampling and truncation

- Sample: take the first N (e.g. 5-8) entries from
  `retrieved_facts`/`comparable_sales` for the response, not all 40-56
  — full counts still reported via `total_provenance_facts`/
  `total_valuation_comps` so the UI can show "5 of 44 sources shown."
- Truncation: `description`/`claim` text cut to ~300 chars with an
  ellipsis if longer; `source_url` never truncated.
- This happens ONLY in `response_models.py`'s construction from
  `PipelineResult` — the underlying `PipelineResult`/agent outputs are
  never mutated.

## Error handling

Per requirements.md: request-shape errors (no file uploaded) still
fail `POST /api/analyze` synchronously with 400. Once a job is running,
errors are captured into `Job.status = FAILED` / `Job.error` /
`Job.failed_stage` inside `execute_job()` (see "Job store" above) —
`GET /api/status/{job_id}` itself returns 200 with a failed-status body,
not an HTTP error code, since successfully reporting "this job failed"
is not itself a server error. Only a genuinely unknown `job_id` returns
404 from the status endpoint.

## CORS

Permissive dev default (`allow_origins=["*"]` or localhost-specific)
for now; note in code comments that this should be tightened to the
actual frontend origin before final submission if time allows.

## Testing approach

- Unit tests: `response_models.py` construction from a mocked
  `PipelineResult` — verify truncation, sampling, timing shape are all
  correct
- Unit tests: `execute_job()` correctly transitions job status
  (queued → running → complete/failed), correctly maps
  `NotArtworkError` and other typed exceptions to `failed` status with
  the right `failed_stage`
- Unit tests: `GET /api/status/{job_id}` returns 404 for an unknown
  job_id, and correctly reflects in-progress `logs` for a running job
- Integration test (marked separately): real `POST /api/analyze` call
  (returns job_id immediately — assert this happens fast, not after a
  60-90s wait) followed by real polling of
  `GET /api/status/{job_id}` until `complete`, against the real
  pipeline