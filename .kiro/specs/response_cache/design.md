# Design: Response Cache

## Cache key

```python
import hashlib
import json

def compute_cache_key(images: list[str], known_title, known_artist, known_period, medium) -> str:
    # images: base64 strings, already what PipelineInput carries
    metadata = {
        "known_title": known_title,
        "known_artist": known_artist,
        "known_period": known_period,
        "medium": medium,
    }
    payload = json.dumps(
        {"images": images, "metadata": metadata}, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

Hashing the base64 strings directly (not re-decoding to raw bytes
first) is sufficient and simpler - identical upload produces identical
base64 output deterministically.

## Storage

```python
# src/artgents/api/cache.py

CACHE_DIR = Path(tempfile.gettempdir()) / "artgents_cache"
CACHE_DIR.mkdir(exist_ok=True)

def get_cached(key: str) -> AnalyzeResponse | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return AnalyzeResponse.model_validate_json(path.read_text())
    except Exception:
        logger.warning("Cache file {} unreadable, treating as miss", path)
        return None

def set_cached(key: str, response: AnalyzeResponse) -> None:
    path = CACHE_DIR / f"{key}.json"
    path.write_text(response.model_dump_json())
```

Using the system temp directory (not a repo-relative path) keeps this
consistent with typical container/serverless filesystem conventions -
writable, cleared automatically on instance recycle, no risk of
accidentally committing cache files to the repo.

## Integration point - execute_job() in api/jobs.py

Cache check happens first, before any Vertex/retrieval calls - a hit
means zero real work, near-instant COMPLETED status:

```python
async def execute_job(job: Job, pipeline_input: PipelineInput) -> None:
    job.status = JobStatus.RUNNING

    cache_key = compute_cache_key(
        pipeline_input.images,
        pipeline_input.known_title,
        pipeline_input.known_artist,
        pipeline_input.known_period,
        pipeline_input.medium,
    )
    cached = get_cached(cache_key)
    if cached is not None:
        job.result = cached
        job.status = JobStatus.COMPLETED
        job.logs.append(ProgressEntry(stage_key="start", message="Loaded from cache."))
        logger.info("Job {} served from cache (key={})", job.id, cache_key)
        return

    def on_progress(stage_key: str, msg: str) -> None:
        job.logs.append(ProgressEntry(stage_key=stage_key, message=msg))

    try:
        pipeline_result = await run_pipeline(pipeline_input, on_progress=on_progress)
        analyze_response = build_analyze_response(pipeline_result)
        job.result = analyze_response
        job.status = JobStatus.COMPLETED
        set_cached(cache_key, analyze_response)  # only cache on success
        logger.info("Job {} completed and cached (key={})", job.id, cache_key)

    except (InvalidImageError, NotArtworkError, CreditExhaustedError,
            VertexCallError, Exception) as exc:
        # existing error-mapping logic unchanged - do NOT cache on any
        # failure path
        ...
```

A miss proceeds exactly as before, with a set_cached() call added only
on the success path (never in any except branch).

## Testing approach

- Unit tests: compute_cache_key() - same input gives same key;
  different metadata gives different key; different images gives
  different key
- Unit tests: get_cached()/set_cached() against a temp directory (not
  the real system temp dir in tests - use tmp_path fixture or
  equivalent) - round-trip write/read, and a corrupted/unreadable
  cache file treated as a miss rather than crashing
- Unit tests: execute_job() with a mocked cache hit - assert
  run_pipeline() is never called, job completes immediately
- Unit tests: execute_job() with a mocked cache miss and successful
  pipeline run - assert set_cached() is called with the right key and
  result
- Unit tests: execute_job() with a mocked pipeline failure - assert
  set_cached() is NOT called