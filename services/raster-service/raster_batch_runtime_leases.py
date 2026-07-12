"""Process-private lease tokens for durable raster batch jobs.

Lease tokens are capabilities and must never be stored in the public job status
payload returned by /jobs/{id}. This map is intentionally process-local; after a
restart the worker obtains a fresh token through PostgreSQL lease recovery.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_tokens: dict[str, str] = {}


def set_token(job_id: str, token: str | None) -> None:
    if not token:
        return
    with _lock:
        _tokens[job_id] = token


def get_token(job_id: str) -> str | None:
    with _lock:
        return _tokens.get(job_id)


def pop_token(job_id: str) -> str | None:
    with _lock:
        return _tokens.pop(job_id, None)


def clear() -> None:
    with _lock:
        _tokens.clear()
