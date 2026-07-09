from __future__ import annotations

import json
import os
from time import monotonic
from typing import Any

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
TTL_S = float(os.getenv("WEATHER_CACHE_TTL_S", "600"))
STALE_TTL_S = float(os.getenv("WEATHER_CACHE_STALE_TTL_S", "3600"))
REDIS_URL = os.getenv("WEATHER_REDIS_URL") or os.getenv("REDIS_URL")
_REDIS_CLIENT: Any | None = None
_REDIS_ERROR: str | None = None


def _redis():
    """Return a Redis client when configured and importable; otherwise memory cache remains active."""
    global _REDIS_CLIENT, _REDIS_ERROR
    if not REDIS_URL:
        return None
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        import redis  # type: ignore

        _REDIS_CLIENT = redis.Redis.from_url(REDIS_URL, socket_timeout=0.25, socket_connect_timeout=0.25)
        _REDIS_CLIENT.ping()
        _REDIS_ERROR = None
        return _REDIS_CLIENT
    except Exception as exc:  # noqa: BLE001 - cache backend must not break weather runtime
        _REDIS_ERROR = str(exc)
        _REDIS_CLIENT = None
        return None


def _fresh_key(key: str) -> str:
    return f"sahool:weather:fresh:{key}"


def _stale_key(key: str) -> str:
    return f"sahool:weather:stale:{key}"


def get(key: str) -> tuple[dict[str, Any] | None, str, int | None]:
    client = _redis()
    if client is not None:
        try:
            raw = client.get(_fresh_key(key))
            if raw:
                payload = json.loads(raw)
                return payload.get("value"), "fresh", int(payload.get("age_hint_s", 0))
            raw = client.get(_stale_key(key))
            if raw:
                payload = json.loads(raw)
                age = int(monotonic() - float(payload.get("stored_monotonic", monotonic())))
                return payload.get("value"), "stale", max(age, int(TTL_S))
            return None, "miss", None
        except Exception as exc:  # noqa: BLE001 - fail open to memory cache
            global _REDIS_ERROR
            _REDIS_ERROR = str(exc)
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
    client = _redis()
    if client is not None:
        payload = json.dumps({"stored_monotonic": monotonic(), "age_hint_s": 0, "value": value}, default=str)
        try:
            client.setex(_fresh_key(key), int(TTL_S), payload)
            client.setex(_stale_key(key), int(STALE_TTL_S), payload)
            return
        except Exception as exc:  # noqa: BLE001
            global _REDIS_ERROR
            _REDIS_ERROR = str(exc)
    _CACHE[key] = (monotonic(), value)


def stats() -> dict[str, Any]:
    client = _redis()
    backend = "redis" if client is not None else "memory"
    payload: dict[str, Any] = {
        "backend": backend,
        "ttl_s": int(TTL_S),
        "stale_ttl_s": int(STALE_TTL_S),
        "redis_configured": bool(REDIS_URL),
    }
    if backend == "memory":
        payload["entries"] = len(_CACHE)
        if _REDIS_ERROR:
            payload["redis_error"] = _REDIS_ERROR
    else:
        payload["entries"] = None
    return payload
