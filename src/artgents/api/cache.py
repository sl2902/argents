"""Local filesystem response cache for pipeline results.

LIMITATION: This is a local filesystem cache using the system temp directory.
On Cloud Run (or any serverless/container deployment target), local disk is
ephemeral — it does not survive a restart, redeploy, or a request landing on
a different instance. This cache is useful WITHIN a single running process
(repeat requests during testing/demo rehearsal won't re-burn Vertex calls)
but should not be relied on to persist across restarts or scale across
multiple instances. A production version would need external persistent
storage (e.g. a GCS bucket, a small database).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from loguru import logger

from artgents.api.response_models import AnalyzeResponse

CACHE_DIR = Path(tempfile.gettempdir()) / "artgents_cache"
CACHE_DIR.mkdir(exist_ok=True)


def compute_cache_key(
    images: list[str],
    known_title: str | None,
    known_artist: str | None,
    known_period: str | None,
    medium: str | None,
) -> str:
    """Compute a deterministic SHA-256 cache key from pipeline inputs.

    Includes both image bytes (as base64 strings) and all optional metadata
    fields — different metadata produces a different key since e.g. known_title
    changes evidence_scope in downstream agents.
    """
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


def get_cached(key: str, cache_dir: Path = CACHE_DIR) -> AnalyzeResponse | None:
    """Retrieve a cached AnalyzeResponse by key, or None on miss.

    A corrupted or unreadable cache file is treated as a miss (logged as
    a warning), never raised as an error.
    """
    path = cache_dir / f"{key}.json"
    if not path.exists():
        return None
    try:
        return AnalyzeResponse.model_validate_json(path.read_text())
    except Exception as exc:
        logger.warning(
            "Cache file {} unreadable ({}), treating as miss", path, exc
        )
        return None


def set_cached(
    key: str, response: AnalyzeResponse, cache_dir: Path = CACHE_DIR
) -> None:
    """Write an AnalyzeResponse to the cache.

    Only call this on successful pipeline completion — never cache failures.
    """
    cache_dir.mkdir(exist_ok=True)
    path = cache_dir / f"{key}.json"
    path.write_text(response.model_dump_json())
