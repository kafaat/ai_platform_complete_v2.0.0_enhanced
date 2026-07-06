"""In-memory single-flight locks/cache state for CDSE tile requests."""

from __future__ import annotations

from typing import Any

cdse_tile_cache: dict[str, tuple[float, str]] = {}
_cdse_cache_lock: Any | None = None
cdse_key_locks: dict[str, Any] = {}


def cdse_lock():
    global _cdse_cache_lock
    import asyncio

    if _cdse_cache_lock is None:
        _cdse_cache_lock = asyncio.Lock()
    return _cdse_cache_lock


def cdse_key_lock(cache_key: str):
    import asyncio

    lock = cdse_key_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        cdse_key_locks[cache_key] = lock
    return lock


def cdse_prune_key_locks_locked() -> None:
    live = set(cdse_tile_cache.keys())
    for key in list(cdse_key_locks.keys()):
        if key not in live:
            cdse_key_locks.pop(key, None)
