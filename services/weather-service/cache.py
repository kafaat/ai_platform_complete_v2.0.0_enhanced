from __future__ import annotations

from time import monotonic
from typing import Any

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
TTL_S = 600.0
STALE_TTL_S = 3600.0


def get(key: str) -> tuple[dict[str, Any] | None, str, int | None]:
    if key not in _CACHE:
        return None, "miss", None
    ts, value = _CACHE[key]
    age = int(monotonic() - ts)
    if age <= TTL_S:
        return value, "fresh", age
    if age <= STALE_TTL_S:
        return value, "stale", age
    _CACHE.pop(key, None)
    return None, "expired", age


def set(key: str, value: dict[str, Any]) -> None:
    _CACHE[key] = (monotonic(), value)


def stats() -> dict[str, Any]:
    return {
        "backend": "memory",
        "entries": len(_CACHE),
        "ttl_s": int(TTL_S),
        "stale_ttl_s": int(STALE_TTL_S),
    }
