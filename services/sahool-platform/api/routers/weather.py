"""api/routers/weather.py — الطقس (Weather: current/forecast/historical)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

ملاحظة: مسارات ``/api/v1/automation/weather/*`` مُستخرَجة سلفاً في
``routers/automation.py`` — هنا فقط مسارات ``/api/v1/weather/*``.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from math import atan, degrees, pi, sinh
from time import monotonic
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from api.service_token_auth import _require_service_token
from api.weather_alerts import derive_weather_alerts

router = APIRouter()


# Cache صغير للبلاطات؛ يقلل طلبات Open-Meteo أثناء التحريك/التكبير.
_WEATHER_TILE_CACHE: dict[str, tuple[float, dict]] = {}
_WEATHER_TILE_METRICS: dict[str, Counter[str]] = {
    "requests": Counter(),
    "cache_states": Counter(),
    "upstream": Counter(),
    "layers": Counter(),
    "operations": Counter(),
}
_WEATHER_TILE_CACHE_TTL_S = 600.0
_WEATHER_TILE_STALE_TTL_S = 3600.0
_WEATHER_REDIS_CLIENT = None
_WEATHER_REDIS_LAST_ERROR: str | None = None
_WEATHER_REDIS_KEY_PREFIX = "sahool:weather:tile"
_ALLOWED_WEATHER_TIMES = {"now", "+1h", "+3h", "+6h", "+12h", "+24h", "+48h"}
_ALLOWED_WEATHER_MODELS = {"best_match", "auto", "gfs_seamless", "ecmwf_ifs04"}
_WEATHER_RATE_WINDOWS: dict[str, tuple[float, int]] = {}
_WEATHER_RATE_REDIS_LAST_ERROR: str | None = None
_WEATHER_RATE_REDIS_KEY_PREFIX = "sahool:weather:rate"
_WEATHER_RATE_LIMITS: dict[str, tuple[int, int]] = {
    # endpoint_group: (max_requests, window_seconds)
    "tile-data": (720, 60),
    "operation-tile-data": (720, 60),
    "tile-series": (180, 60),
    "probe": (180, 60),
    "operation-window": (120, 60),
    "operation-plan": (90, 60),
    "field-weather-summary": (120, 60),
    "weather-action-recommendation": (90, 60),
    "current": (180, 60),
    "forecast": (120, 60),
    "historical": (60, 60),
    "task-from-operation-plan": (45, 60),
    "recommendation-from-operation-plan": (45, 60),
    "default": (300, 60),
}


class WeatherTaskFromPlanRequest(BaseModel):
    field_id: str = Field(..., min_length=1, max_length=80)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    operation: Literal["spraying", "irrigation", "harvesting", "sowing"] = "spraying"
    hours: str = "0,1,3,6,12,24,48"
    model: str = "best_match"
    assigned_to: str | None = None
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    dry_run: bool = False
    notes: str | None = None


class WeatherRecommendationFromPlanRequest(BaseModel):
    field_id: str = Field(..., min_length=1, max_length=80)
    farm_id: str | None = None
    crop: str | None = None
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    operations: str = "spraying,irrigation,harvesting,sowing"
    hours: str = "0,1,3,6,12,24,48"
    model: str = "best_match"
    dry_run: bool = False


def _metric_inc(bucket: str, key: str, amount: int = 1) -> None:
    counter = _WEATHER_TILE_METRICS.setdefault(bucket, Counter())
    counter[str(key)] += amount


def _record_weather_observation(
    endpoint: str,
    *,
    cache_state: str | None = None,
    upstream_error: str | None = None,
    layer: str | None = None,
    operation: str | None = None,
) -> None:
    """يسجل عدادات خفيفة بلا تبعية Prometheus/Redis.

    الهدف هو كشف سلوك طبقة الطقس أثناء التطوير وبيئات Docker البسيطة:
    cache hit/miss، fallback، وأكثر الطبقات/العمليات استخداماً. في الإنتاج يمكن
    ربط هذه القيم لاحقاً بـPrometheus أو Redis بدون تغيير عقود الواجهة.
    """
    _metric_inc("requests", endpoint)
    if cache_state:
        _metric_inc("cache_states", cache_state)
    if upstream_error:
        _metric_inc("upstream", "error")
    elif cache_state in {"refreshed", "fresh", "stale_fallback"}:
        _metric_inc("upstream", "served")
    if layer:
        _metric_inc("layers", layer)
    if operation:
        _metric_inc("operations", operation)


def _metrics_bucket(bucket: str) -> dict[str, int]:
    return dict(_WEATHER_TILE_METRICS.get(bucket, Counter()))


def _weather_cache_backend_config() -> dict:
    """Runtime cache backend config.

    Defaults to in-memory cache for local/dev. Production can opt into Redis via:
    SAHOOL_WEATHER_CACHE_BACKEND=redis and SAHOOL_WEATHER_REDIS_URL=redis://...
    The default fallback keeps the weather layer usable when Redis is unavailable.
    """
    backend = (
        (
            os.getenv("SAHOOL_WEATHER_CACHE_BACKEND")
            or os.getenv("WEATHER_CACHE_BACKEND")
            or "memory"
        )
        .strip()
        .lower()
    )
    if backend not in {"memory", "redis"}:
        backend = "memory"
    redis_url = (
        os.getenv("SAHOOL_WEATHER_REDIS_URL")
        or os.getenv("WEATHER_REDIS_URL")
        or os.getenv("REDIS_URL")
    )
    fallback_raw = os.getenv("SAHOOL_WEATHER_REDIS_FALLBACK_MEMORY", "1").strip().lower()
    return {
        "backend": backend,
        "redis_configured": bool(redis_url),
        "redis_url_present": bool(redis_url),
        "fallback_to_memory": fallback_raw not in {"0", "false", "no", "off"},
        "key_prefix": _WEATHER_REDIS_KEY_PREFIX,
        "ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
        "stale_ttl_s": int(_WEATHER_TILE_STALE_TTL_S),
    }


async def _weather_redis_client():
    """Return an optional redis.asyncio client without making Redis a hard dependency."""
    global _WEATHER_REDIS_CLIENT, _WEATHER_REDIS_LAST_ERROR
    cfg = _weather_cache_backend_config()
    if cfg["backend"] != "redis":
        return None
    if _WEATHER_REDIS_CLIENT is not None:
        return _WEATHER_REDIS_CLIENT
    redis_url = (
        os.getenv("SAHOOL_WEATHER_REDIS_URL")
        or os.getenv("WEATHER_REDIS_URL")
        or os.getenv("REDIS_URL")
    )
    if not redis_url:
        _WEATHER_REDIS_LAST_ERROR = "Redis backend selected but no Redis URL is configured."
        _metric_inc("cache_backends", "redis_missing_url")
        return None
    try:
        import redis.asyncio as redis  # type: ignore

        _WEATHER_REDIS_CLIENT = redis.from_url(redis_url, decode_responses=True)
        _WEATHER_REDIS_LAST_ERROR = None
        _metric_inc("cache_backends", "redis_client_created")
        return _WEATHER_REDIS_CLIENT
    except Exception as exc:  # pragma: no cover - depends on optional dependency
        _WEATHER_REDIS_LAST_ERROR = str(exc)
        _metric_inc("cache_backends", "redis_import_error")
        return None


def _redis_cache_key(key: str) -> str:
    return f"{_WEATHER_REDIS_KEY_PREFIX}:{key}"


def _cache_state_from_ts(ts: float) -> tuple[str, int | None]:
    age = monotonic() - ts
    if age < _WEATHER_TILE_CACHE_TTL_S:
        return "fresh", int(age)
    if age < _WEATHER_TILE_STALE_TTL_S:
        return "stale", int(age)
    return "expired", int(age)


async def _cache_get_async(key: str) -> tuple[dict | None, str, int | None]:
    """Get a weather cache entry from Redis when enabled, otherwise memory.

    The return contract intentionally matches the legacy in-memory helper:
    (sample, state, age_s). States: fresh, stale, expired, miss, backend_error.
    """
    cfg = _weather_cache_backend_config()
    if cfg["backend"] == "redis":
        client = await _weather_redis_client()
        if client is not None:
            try:
                raw = await client.get(_redis_cache_key(key))
                if raw:
                    payload = json.loads(raw)
                    state, age = _cache_state_from_ts(float(payload.get("ts", 0)))
                    if state in {"fresh", "stale"}:
                        _metric_inc("cache_backends", "redis_hit")
                        return payload.get("sample") or {}, state, age
                    _metric_inc("cache_backends", "redis_expired")
                    return None, "expired", age
                _metric_inc("cache_backends", "redis_miss")
                if not cfg["fallback_to_memory"]:
                    return None, "miss", None
            except Exception as exc:
                global _WEATHER_REDIS_LAST_ERROR
                _WEATHER_REDIS_LAST_ERROR = str(exc)
                _metric_inc("cache_backends", "redis_error")
                if not cfg["fallback_to_memory"]:
                    return None, "backend_error", None
        elif not cfg["fallback_to_memory"]:
            return None, "backend_error", None
    return _cache_get(key)


async def _cache_set_async(key: str, sample: dict) -> None:
    """Set a weather cache entry in Redis when enabled and keep memory fallback hot."""
    cfg = _weather_cache_backend_config()
    wrote_redis = False
    if cfg["backend"] == "redis":
        client = await _weather_redis_client()
        if client is not None:
            try:
                payload = json.dumps({"ts": monotonic(), "sample": sample}, ensure_ascii=False)
                await client.setex(_redis_cache_key(key), int(_WEATHER_TILE_STALE_TTL_S), payload)
                wrote_redis = True
                _metric_inc("cache_backends", "redis_set")
            except Exception as exc:
                global _WEATHER_REDIS_LAST_ERROR
                _WEATHER_REDIS_LAST_ERROR = str(exc)
                _metric_inc("cache_backends", "redis_error")
                if not cfg["fallback_to_memory"]:
                    return
    if cfg["backend"] == "memory" or cfg["fallback_to_memory"] or not wrote_redis:
        _cache_set(key, sample)


def _weather_cache_backend_status() -> dict:
    cfg = _weather_cache_backend_config()
    return {
        **cfg,
        "redis_last_error": _WEATHER_REDIS_LAST_ERROR,
        "memory_items": len(_WEATHER_TILE_CACHE),
        "mode": cfg["backend"],
        "effective_backend": "redis+memory-fallback"
        if cfg["backend"] == "redis" and cfg["fallback_to_memory"]
        else cfg["backend"],
    }


def _weather_rate_backend_config() -> dict:
    """Runtime rate-limit backend config.

    Production can opt into Redis with SAHOOL_WEATHER_RATE_LIMIT_BACKEND=redis.
    When unset, the limiter remains in-process for local/dev compatibility.
    """
    backend = (
        (
            os.getenv("SAHOOL_WEATHER_RATE_LIMIT_BACKEND")
            or os.getenv("WEATHER_RATE_LIMIT_BACKEND")
            or "memory"
        )
        .strip()
        .lower()
    )
    if backend not in {"memory", "redis"}:
        backend = "memory"
    fallback_raw = os.getenv("SAHOOL_WEATHER_RATE_LIMIT_REDIS_FALLBACK_MEMORY", "1").strip().lower()
    redis_url = (
        os.getenv("SAHOOL_WEATHER_RATE_LIMIT_REDIS_URL")
        or os.getenv("SAHOOL_WEATHER_REDIS_URL")
        or os.getenv("WEATHER_REDIS_URL")
        or os.getenv("REDIS_URL")
    )
    return {
        "backend": backend,
        "redis_configured": bool(redis_url),
        "fallback_to_memory": fallback_raw not in {"0", "false", "no", "off"},
        "key_prefix": _WEATHER_RATE_REDIS_KEY_PREFIX,
    }


def _weather_rate_backend_status() -> dict:
    cfg = _weather_rate_backend_config()
    return {
        **cfg,
        "redis_last_error": _WEATHER_RATE_REDIS_LAST_ERROR,
        "memory_buckets": len(_WEATHER_RATE_WINDOWS),
        "effective_backend": "redis+memory-fallback"
        if cfg["backend"] == "redis" and cfg["fallback_to_memory"]
        else cfg["backend"],
    }


def _redis_rate_key(key: str) -> str:
    return f"{_WEATHER_RATE_REDIS_KEY_PREFIX}:{key}"


def _tenant_id_from_request(request: Request | None) -> str:
    if request is None:
        return "direct"
    return (
        request.headers.get("x-tenant-id")
        or request.headers.get("x-sahool-tenant")
        or request.query_params.get("tenant_id")
        or "anon"
    )


def _actor_id_from_request(request: Request | None) -> str:
    if request is None:
        return "direct"
    auth = request.headers.get("authorization")
    user_hint = request.headers.get("x-user-id") or request.headers.get("x-sahool-user")
    if user_hint:
        return f"user:{user_hint[:96]}"
    if auth:
        return f"auth:{abs(hash(auth)) % 1_000_000}"
    host = getattr(getattr(request, "client", None), "host", None) or "unknown"
    return f"ip:{host}"


def _tile_lon_bounds(x: int, z: int) -> tuple[float, float]:
    return _tile_lon(x, z), _tile_lon(x + 1, z)


def _tile_lat_bounds(y: int, z: int) -> tuple[float, float]:
    north = _tile_lat(y, z)
    south = _tile_lat(y + 1, z)
    return north, south


def _tile_interpolation_points(z: int, x: int, y: int) -> list[dict]:
    """Return stable sample points inside a WebMercator tile for smooth SAHOOL rendering."""
    west, east = _tile_lon_bounds(x, z)
    north, south = _tile_lat_bounds(y, z)
    lat_span = north - south
    lon_span = east - west
    # Inset points avoid neighboring-tile discontinuity and reduce redundant edge calls.
    return [
        {
            "id": "nw",
            "u": 0.18,
            "v": 0.18,
            "lat": north - lat_span * 0.18,
            "lon": west + lon_span * 0.18,
        },
        {
            "id": "ne",
            "u": 0.82,
            "v": 0.18,
            "lat": north - lat_span * 0.18,
            "lon": west + lon_span * 0.82,
        },
        {
            "id": "sw",
            "u": 0.18,
            "v": 0.82,
            "lat": north - lat_span * 0.82,
            "lon": west + lon_span * 0.18,
        },
        {
            "id": "se",
            "u": 0.82,
            "v": 0.82,
            "lat": north - lat_span * 0.82,
            "lon": west + lon_span * 0.82,
        },
        {
            "id": "center",
            "u": 0.50,
            "v": 0.50,
            "lat": (north + south) / 2.0,
            "lon": (west + east) / 2.0,
        },
    ]


async def _weather_tile_interpolation_payload(
    *,
    z: int,
    x: int,
    y: int,
    layer: str,
    time: str,
    model: str,
    operation: str | None = None,
) -> tuple[dict | None, str, int | None, str | None, dict | None]:
    """Fetch a lightweight 2x2+center sample set for smoother client SVG tiles.

    Returns center sample, aggregate cache state/age/error, and an interpolation payload.
    If all points fail, callers should fall back to the legacy center-only path.
    """
    points: list[dict] = []
    cache_states: list[str] = []
    ages: list[int] = []
    errors: list[str] = []
    center_sample: dict | None = None
    prefix = f"interp:{operation or layer}:z{z}:x{x}:y{y}"
    for pt in _tile_interpolation_points(z, x, y):
        try:
            sample, state, age, upstream_error = await _get_weather_sample_cached(
                float(pt["lat"]), float(pt["lon"]), time, model, f"{prefix}:{pt['id']}"
            )
            if upstream_error:
                errors.append(f"{pt['id']}: {upstream_error}")
            value = (
                _safe_layer_value(layer, sample)
                if operation is None
                else _operation_suitability(sample, operation)["score"]
            )
            if pt["id"] == "center":
                center_sample = sample
            cache_states.append(state)
            if age is not None:
                ages.append(int(age))
            points.append(
                {
                    "id": pt["id"],
                    "u": pt["u"],
                    "v": pt["v"],
                    "lat": round(float(pt["lat"]), 6),
                    "lon": round(float(pt["lon"]), 6),
                    "value": value,
                    "cache_state": state,
                }
            )
        except Exception as exc:  # keep the tile usable when a sub-point fails
            errors.append(f"{pt['id']}: {exc}")
    if not points:
        return None, "miss", None, "; ".join(errors) if errors else None, None
    numeric_values = [p["value"] for p in points if isinstance(p.get("value"), (int, float))]
    interp = {
        "mode": "bilinear_2x2_center",
        "quality": "smooth" if len(points) >= 5 else "partial",
        "point_count": len(points),
        "average_value": round(sum(numeric_values) / len(numeric_values), 4)
        if numeric_values
        else None,
        "points": points,
    }
    if center_sample is None:
        center_sample = {}
    if "stale_fallback" in cache_states or "stale" in cache_states:
        cache_state = "stale_fallback" if errors else "stale"
    elif "refreshed" in cache_states:
        cache_state = "refreshed"
    elif all(state == "fresh" for state in cache_states):
        cache_state = "fresh"
    else:
        cache_state = "partial"
    return (
        center_sample,
        cache_state,
        max(ages) if ages else None,
        "; ".join(errors) if errors else None,
        interp,
    )


def _memory_rate_limit_result(request: Request | None, endpoint: str) -> dict:
    limit, window_s = _WEATHER_RATE_LIMITS.get(endpoint, _WEATHER_RATE_LIMITS["default"])
    key = _rate_key(request, endpoint)
    now = monotonic()
    start, count = _WEATHER_RATE_WINDOWS.get(key, (now, 0))
    if now - start >= window_s:
        start, count = now, 0
    count += 1
    _WEATHER_RATE_WINDOWS[key] = (start, count)
    retry_after = max(1, int(window_s - (now - start)))
    remaining = max(0, limit - count)
    return {
        "allowed": count <= limit,
        "limit": limit,
        "window_s": window_s,
        "remaining": remaining,
        "retry_after": retry_after,
        "reset_s": retry_after,
        "backend": "memory",
    }


async def _redis_rate_limit_result(request: Request | None, endpoint: str) -> dict | None:
    global _WEATHER_RATE_REDIS_LAST_ERROR
    cfg = _weather_rate_backend_config()
    if cfg["backend"] != "redis":
        return None
    client = _WEATHER_REDIS_CLIENT
    if client is None:
        redis_url = (
            os.getenv("SAHOOL_WEATHER_RATE_LIMIT_REDIS_URL")
            or os.getenv("SAHOOL_WEATHER_REDIS_URL")
            or os.getenv("WEATHER_REDIS_URL")
            or os.getenv("REDIS_URL")
        )
        if not redis_url:
            _WEATHER_RATE_REDIS_LAST_ERROR = (
                "Redis rate backend selected but no Redis URL is configured."
            )
            _metric_inc("rate_limit_backends", "redis_missing_url")
            return None
        try:
            import redis.asyncio as redis  # type: ignore

            client = redis.from_url(redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - optional dependency
            _WEATHER_RATE_REDIS_LAST_ERROR = str(exc)
            _metric_inc("rate_limit_backends", "redis_import_error")
            return None
    limit, window_s = _WEATHER_RATE_LIMITS.get(endpoint, _WEATHER_RATE_LIMITS["default"])
    tenant = _tenant_id_from_request(request)
    actor = _actor_id_from_request(request)
    key = _redis_rate_key(f"{endpoint}:{tenant}:{actor}")
    try:
        count = int(await client.incr(key))
        if count == 1:
            await client.expire(key, int(window_s))
        ttl = int(await client.ttl(key)) if hasattr(client, "ttl") else int(window_s)
        if ttl < 0:
            ttl = int(window_s)
        _WEATHER_RATE_REDIS_LAST_ERROR = None
        _metric_inc("rate_limit_backends", "redis_allowed" if count <= limit else "redis_limited")
        return {
            "allowed": count <= limit,
            "limit": limit,
            "window_s": window_s,
            "remaining": max(0, limit - count),
            "retry_after": max(1, ttl),
            "reset_s": max(1, ttl),
            "backend": "redis",
        }
    except Exception as exc:
        _WEATHER_RATE_REDIS_LAST_ERROR = str(exc)
        _metric_inc("rate_limit_backends", "redis_error")
        return None


def _apply_rate_limit_headers(response: Response | None, result: dict) -> None:
    if response is None:
        return
    response.headers["X-RateLimit-Limit"] = str(result.get("limit", ""))
    response.headers["X-RateLimit-Remaining"] = str(result.get("remaining", ""))
    response.headers["X-RateLimit-Reset"] = str(result.get("reset_s", ""))
    response.headers["X-RateLimit-Backend"] = str(result.get("backend", "memory"))


async def _enforce_weather_rate_limit_async(
    request: Request | None, endpoint: str, response: Response | None = None
) -> dict:
    cfg = _weather_rate_backend_config()
    result = await _redis_rate_limit_result(request, endpoint)
    if result is None:
        if cfg["backend"] == "redis" and not cfg["fallback_to_memory"]:
            result = {
                "allowed": False,
                "limit": 0,
                "window_s": 0,
                "remaining": 0,
                "retry_after": 30,
                "reset_s": 30,
                "backend": "redis_unavailable",
            }
        else:
            result = _memory_rate_limit_result(request, endpoint)
    _apply_rate_limit_headers(response, result)
    if not result["allowed"]:
        retry_after = int(result.get("retry_after") or 1)
        _metric_inc("rate_limited", endpoint)
        raise HTTPException(
            status_code=429,
            detail={
                "message_ar": "تم تجاوز حد طلبات طبقة الطقس مؤقتاً.",
                "endpoint": endpoint,
                "limit": result.get("limit"),
                "window_s": result.get("window_s"),
                "retry_after_s": retry_after,
                "backend": result.get("backend"),
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(result.get("limit", "")),
                "X-RateLimit-Remaining": str(result.get("remaining", "")),
                "X-RateLimit-Reset": str(result.get("reset_s", "")),
                "X-RateLimit-Backend": str(result.get("backend", "memory")),
            },
        )
    return result


def _rate_key(request: Request | None, endpoint: str) -> str:
    tenant = _tenant_id_from_request(request)
    actor = _actor_id_from_request(request)
    return f"{endpoint}:{tenant}:{actor}"


def _enforce_weather_rate_limit(request: Request | None, endpoint: str) -> None:
    """Synchronous memory limiter retained for unit tests and direct local calls."""
    result = _memory_rate_limit_result(request, endpoint)
    if not result["allowed"]:
        retry_after = int(result.get("retry_after") or 1)
        _metric_inc("rate_limited", endpoint)
        raise HTTPException(
            status_code=429,
            detail={
                "message_ar": "تم تجاوز حد طلبات طبقة الطقس مؤقتاً.",
                "endpoint": endpoint,
                "limit": result.get("limit"),
                "window_s": result.get("window_s"),
                "retry_after_s": retry_after,
                "backend": result.get("backend"),
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(result.get("limit", "")),
                "X-RateLimit-Remaining": str(result.get("remaining", "")),
                "X-RateLimit-Reset": str(result.get("reset_s", "")),
                "X-RateLimit-Backend": str(result.get("backend", "memory")),
            },
        )


def _rate_dependency(endpoint: str):
    async def _dep(request: Request, response: Response):
        await _enforce_weather_rate_limit_async(request, endpoint, response)

    return _dep


def _prom_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _prom_counter_lines(
    metric: str, help_text: str, label_name: str, values: dict[str, int]
) -> list[str]:
    lines = [f"# HELP {metric} {help_text}", f"# TYPE {metric} counter"]
    for key, value in sorted(values.items()):
        lines.append(f'{metric}{{{label_name}="{_prom_label(key)}"}} {int(value)}')
    return lines


def _weather_metrics_prometheus() -> str:
    cache = _weather_cache_snapshot()
    lines: list[str] = [
        "# HELP sahool_weather_cache_items Current weather cache item count by state",
        "# TYPE sahool_weather_cache_items gauge",
        f'sahool_weather_cache_items{{state="total"}} {cache["items"]}',
        f'sahool_weather_cache_items{{state="fresh"}} {cache["fresh_items"]}',
        f'sahool_weather_cache_items{{state="stale"}} {cache["stale_items"]}',
        f'sahool_weather_cache_items{{state="expired"}} {cache["expired_items"]}',
        "# HELP sahool_weather_cache_ttl_seconds Weather cache TTL settings",
        "# TYPE sahool_weather_cache_ttl_seconds gauge",
        f'sahool_weather_cache_ttl_seconds{{kind="fresh"}} {cache["ttl_s"]}',
        f'sahool_weather_cache_ttl_seconds{{kind="stale"}} {cache["stale_ttl_s"]}',
    ]
    lines.extend(
        _prom_counter_lines(
            "sahool_weather_requests_total",
            "Total weather engine requests by logical endpoint",
            "endpoint",
            _metrics_bucket("requests"),
        )
    )
    lines.extend(
        _prom_counter_lines(
            "sahool_weather_cache_states_total",
            "Total weather engine responses by cache state",
            "state",
            _metrics_bucket("cache_states"),
        )
    )
    lines.extend(
        _prom_counter_lines(
            "sahool_weather_upstream_total",
            "Total weather upstream outcomes",
            "outcome",
            _metrics_bucket("upstream"),
        )
    )
    lines.extend(
        _prom_counter_lines(
            "sahool_weather_layers_total",
            "Total weather layer usage",
            "layer",
            _metrics_bucket("layers"),
        )
    )
    lines.extend(
        _prom_counter_lines(
            "sahool_weather_operations_total",
            "Total weather operation usage",
            "operation",
            _metrics_bucket("operations"),
        )
    )
    lines.extend(
        _prom_counter_lines(
            "sahool_weather_rate_limited_total",
            "Total weather requests rejected by in-process rate limiter",
            "endpoint",
            _metrics_bucket("rate_limited"),
        )
    )
    lines.extend(
        _prom_counter_lines(
            "sahool_weather_cache_backend_total",
            "Total weather cache backend events",
            "event",
            _metrics_bucket("cache_backends"),
        )
    )
    lines.extend(
        _prom_counter_lines(
            "sahool_weather_rate_limit_backend_total",
            "Total weather rate-limit backend events",
            "event",
            _metrics_bucket("rate_limit_backends"),
        )
    )
    return "\n".join(lines) + "\n"


def _prune_weather_cache(expired_only: bool = True) -> dict:
    now = monotonic()
    before = len(_WEATHER_TILE_CACHE)
    removed = 0
    for key, (ts, _sample) in list(_WEATHER_TILE_CACHE.items()):
        age = now - ts
        should_remove = (
            age >= _WEATHER_TILE_STALE_TTL_S if expired_only else age >= _WEATHER_TILE_CACHE_TTL_S
        )
        if should_remove:
            _WEATHER_TILE_CACHE.pop(key, None)
            removed += 1
    return {
        "before": before,
        "removed": removed,
        "after": len(_WEATHER_TILE_CACHE),
        "expired_only": expired_only,
        "cache": _weather_cache_snapshot(),
    }


def _weather_cache_snapshot() -> dict:
    now = monotonic()
    fresh = sum(1 for ts, _ in _WEATHER_TILE_CACHE.values() if now - ts < _WEATHER_TILE_CACHE_TTL_S)
    stale = sum(
        1
        for ts, _ in _WEATHER_TILE_CACHE.values()
        if _WEATHER_TILE_CACHE_TTL_S <= now - ts < _WEATHER_TILE_STALE_TTL_S
    )
    expired = max(0, len(_WEATHER_TILE_CACHE) - fresh - stale)
    return {
        "items": len(_WEATHER_TILE_CACHE),
        "fresh_items": fresh,
        "stale_items": stale,
        "expired_items": expired,
        "ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
        "stale_ttl_s": int(_WEATHER_TILE_STALE_TTL_S),
        "max_items_soft": 2048,
        "rate_limit_buckets": len(_WEATHER_RATE_WINDOWS),
        "backend": _weather_cache_backend_status(),
        "rate_limit_backend": _weather_rate_backend_status(),
    }


def _weather_engine_self_checks() -> dict:
    """Production self-checks that do not call external providers.

    هذه الفحوصات تتحقق من سلامة المنطق المحلي: WebMercator tile math، تعريفات
    الطبقات، محرك صلاحية العمليات، الكاش، ومخرجات Prometheus. عدم استدعاء
    Open-Meteo مقصود حتى تكون readyz مستقرة ولا تستنزف quota.
    """
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}

    try:
        lat, lon = _tile_center(6, 38, 27)
        checks["tile_center"] = -90 <= lat <= 90 and -180 <= lon <= 180
        details["tile_center"] = {"lat": round(lat, 6), "lon": round(lon, 6)}
    except Exception as exc:
        checks["tile_center"] = False
        details["tile_center_error"] = str(exc)

    checks["layers_configured"] = len(_ALLOWED_WEATHER_TILE_LAYERS) >= 9
    details["layers_count"] = len(_ALLOWED_WEATHER_TILE_LAYERS)

    checks["times_configured"] = {"now", "+24h", "+48h"}.issubset(_ALLOWED_WEATHER_TIMES)
    details["times_count"] = len(_ALLOWED_WEATHER_TIMES)

    try:
        decision = _operation_suitability(
            {
                "temperature_2m_c": 24,
                "relative_humidity_2m_pct": 52,
                "wind_speed_10m_kmh": 9,
                "wind_gusts_10m_kmh": 14,
                "precipitation_mm": 0,
                "soil_moisture_0_10cm_m3_m3": 0.18,
                "vapour_pressure_deficit_kpa": 1.4,
            },
            "spraying",
        )
        checks["operation_engine"] = (
            0 <= float(decision.get("score", -1)) <= 1 and "suitability" in decision
        )
        details["operation_engine"] = decision
    except Exception as exc:
        checks["operation_engine"] = False
        details["operation_engine_error"] = str(exc)

    try:
        prom = _weather_metrics_prometheus()
        checks["prometheus_export"] = "sahool_weather_cache_items" in prom and "# TYPE" in prom
    except Exception as exc:
        checks["prometheus_export"] = False
        details["prometheus_export_error"] = str(exc)

    checks["cache_accounting"] = {"items", "fresh_items", "stale_items", "expired_items"}.issubset(
        _weather_cache_snapshot().keys()
    )
    checks["rate_limits_configured"] = all(
        v[0] > 0 and v[1] > 0 for v in _WEATHER_RATE_LIMITS.values()
    )
    details["rate_limits"] = _WEATHER_RATE_LIMITS
    passed = sum(1 for ok in checks.values() if ok)
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "status": "ok" if not failed else "degraded",
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "details": details,
    }


def _weather_runtime_readiness() -> dict:
    from api.connectors.openmeteo import openmeteo_breaker_state

    self_checks = _weather_engine_self_checks()
    breaker = openmeteo_breaker_state()
    cache = _weather_cache_snapshot()
    degraded_reasons: list[str] = []
    if self_checks["status"] != "ok":
        degraded_reasons.append("self_checks_failed")
    if str(breaker.get("state", "")).lower() in {"open", "tripped"}:
        degraded_reasons.append("openmeteo_breaker_open")
    # Cache pressure is not a hard failure because pruning can recover it.
    if cache["items"] > cache["max_items_soft"]:
        degraded_reasons.append("weather_cache_over_soft_limit")
    return {
        "status": "ready" if not degraded_reasons else "degraded",
        "service": "weather-engine",
        "provider": "open-meteo",
        "rendered_by": "sahool",
        "breaker": breaker,
        "cache": cache,
        "self_checks": self_checks,
        "degraded_reasons": degraded_reasons,
    }


def _registered_weather_routes() -> dict[str, list[str]]:
    """Returns registered weather routes from this router without depending on app startup."""
    routes: dict[str, list[str]] = {}
    for route in getattr(router, "routes", []):
        path = getattr(route, "path", "")
        methods = sorted(getattr(route, "methods", set()) or [])
        if path.startswith("/api/v1/weather"):
            routes[path] = methods
    return routes


def _weather_runtime_contract() -> dict:
    """Static runtime contract for UI/API integration checks.

    This is intentionally local-only: it verifies the API route table, logical
    guards, and frontend-facing contracts without calling Open-Meteo or the DB.
    """
    registered = _registered_weather_routes()
    required = {
        "/api/v1/weather/layers": ["GET"],
        "/api/v1/weather/tile-data/{z}/{x}/{y}": ["GET"],
        "/api/v1/weather/operation-tile-data/{z}/{x}/{y}": ["GET"],
        "/api/v1/weather/probe": ["GET"],
        "/api/v1/weather/operation-window": ["GET"],
        "/api/v1/weather/operation-plan": ["GET"],
        "/api/v1/weather/action-recommendation": ["GET"],
        "/api/v1/weather/tasks/from-operation-plan": ["POST"],
        "/api/v1/weather/recommendations/from-operation-plan": ["POST"],
        "/api/v1/weather/field-weather-summary": ["GET"],
        "/api/v1/weather/readyz": ["GET"],
        "/api/v1/weather/self-test": ["GET"],
        "/api/v1/weather/observability": ["GET"],
        "/api/v1/weather/metrics.prom": ["GET"],
        "/api/v1/weather/runtime-smoke-plan": ["GET"],
    }
    endpoints = []
    missing: list[str] = []
    for path, methods in required.items():
        actual = registered.get(path, [])
        ok = all(method in actual for method in methods)
        if not ok:
            missing.append(path)
        endpoints.append({"path": path, "methods": methods, "registered_methods": actual, "ok": ok})

    guards = {
        "rate_limit_enabled": all(
            k in _WEATHER_RATE_LIMITS
            for k in [
                "tile-data",
                "operation-plan",
                "weather-action-recommendation",
                "task-from-operation-plan",
                "recommendation-from-operation-plan",
            ]
        ),
        "cache_enabled": _WEATHER_TILE_CACHE_TTL_S > 0
        and _WEATHER_TILE_STALE_TTL_S > _WEATHER_TILE_CACHE_TTL_S,
        "metrics_enabled": "sahool_weather_requests_total" in _weather_metrics_prometheus(),
        "action_bridge_enabled": "/api/v1/weather/action-recommendation" in registered,
    }
    frontend_contract = {
        "tile_layer_module": "frontend/src/components/maphub/weather/WeatherTileLayer.ts",
        "layer_panel_module": "frontend/src/components/maphub/weather/WeatherLayerPanel.ts",
        "probe_popup_module": "frontend/src/components/maphub/weather/WeatherProbePopup.ts",
        "expected_probe_actions": [
            "/api/v1/weather/action-recommendation",
            "/api/v1/weather/tasks/from-operation-plan",
            "/api/v1/weather/recommendations/from-operation-plan",
        ],
    }
    failed_guards = [name for name, ok in guards.items() if not ok]
    return {
        "status": "ok" if not missing and not failed_guards else "degraded",
        "service": "weather-engine",
        "endpoints": endpoints,
        "missing_endpoints": missing,
        "guards": guards,
        "failed_guards": failed_guards,
        "frontend_contract": frontend_contract,
    }


def _weather_env_doctor() -> dict:
    """Local configuration doctor for production/runtime operators.

    Does not reveal secrets and does not perform external I/O. It reports whether
    the weather engine has safe defaults for cache, rate limits, observability,
    and action-bridge execution.
    """
    contract = _weather_runtime_contract()
    checks = {
        "cache_ttl_valid": _WEATHER_TILE_CACHE_TTL_S >= 60
        and _WEATHER_TILE_STALE_TTL_S >= _WEATHER_TILE_CACHE_TTL_S,
        "cache_backend_valid": (
            _weather_cache_backend_config()["backend"] == "memory"
            or _weather_cache_backend_config()["redis_configured"]
            or _weather_cache_backend_config()["fallback_to_memory"]
        ),
        "rate_limits_valid": all(
            limit > 0 and window > 0 for limit, window in _WEATHER_RATE_LIMITS.values()
        ),
        "rate_limit_backend_valid": (
            _weather_rate_backend_config()["backend"] == "memory"
            or _weather_rate_backend_config()["redis_configured"]
            or _weather_rate_backend_config()["fallback_to_memory"]
        ),
        "high_volume_tiles_limited": _WEATHER_RATE_LIMITS.get("tile-data", (0, 0))[0] <= 2000,
        "action_endpoints_limited": _WEATHER_RATE_LIMITS.get("task-from-operation-plan", (9999, 0))[
            0
        ]
        <= 120,
        "observability_registered": "/api/v1/weather/metrics.prom" in _registered_weather_routes(),
        "readiness_registered": "/api/v1/weather/readyz" in _registered_weather_routes(),
        "runtime_contract_ok": contract["status"] == "ok",
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "status": "ok" if not failed else "degraded",
        "service": "weather-engine",
        "checks": checks,
        "failed": failed,
        "settings": {
            "cache_ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
            "stale_ttl_s": int(_WEATHER_TILE_STALE_TTL_S),
            "rate_limits": {
                key: {"limit": value[0], "window_s": value[1]}
                for key, value in _WEATHER_RATE_LIMITS.items()
            },
            "rate_limit_backend": _weather_rate_backend_status(),
        },
        "recommended_runtime_checks": [
            "GET /api/v1/weather/readyz",
            "GET /api/v1/weather/self-test",
            "GET /api/v1/weather/runtime-contract",
            "GET /api/v1/weather/runtime-smoke-plan",
            "GET /api/v1/weather/metrics.prom",
            "GET /api/v1/weather/tile-cache/backend",
        ],
    }


def _weather_runtime_smoke_plan() -> dict:
    """Operator-oriented smoke plan for Docker/Compose/Kubernetes verification.

    This is a contract artifact, not an external probe: it gives deterministic
    commands/endpoints that can be executed after `docker compose up` or after a
    deployment. It intentionally avoids touching Open-Meteo or the database.
    """
    base = "/api/v1/weather"
    return {
        "status": "ok",
        "service": "weather-engine",
        "purpose": "post-deploy smoke verification for MapHub weather runtime",
        "no_external_io": True,
        "critical_endpoints": [
            {
                "method": "GET",
                "path": f"{base}/readyz",
                "expected": [200, 503],
                "why": "readiness gate; 503 is acceptable only when breaker is intentionally open",
            },
            {
                "method": "GET",
                "path": f"{base}/self-test",
                "expected": [200],
                "why": "local engine self-checks",
            },
            {
                "method": "GET",
                "path": f"{base}/runtime-contract",
                "expected": [200],
                "why": "UI/API route contract",
            },
            {
                "method": "GET",
                "path": f"{base}/env-doctor",
                "expected": [200],
                "why": "configuration guardrails",
            },
            {
                "method": "GET",
                "path": f"{base}/layers",
                "expected": [200],
                "why": "frontend weather manifest",
            },
            {
                "method": "GET",
                "path": f"{base}/tile-cache/stats",
                "expected": [200],
                "why": "cache accounting",
            },
            {
                "method": "GET",
                "path": f"{base}/metrics.prom",
                "expected": [200],
                "why": "Prometheus scrape",
            },
        ],
        "sample_runtime_endpoints": [
            {
                "method": "GET",
                "path": f"{base}/tile-data/8/155/108?layer=temperature&time=now&model=best_match&interpolation=grid",
                "expected": [200, 429, 502],
                "why": "real tile path; may need network unless cached",
            },
            {
                "method": "GET",
                "path": f"{base}/operation-plan?lat=15.37&lon=44.19&operations=spraying,irrigation&hours=0,3,6&model=best_match",
                "expected": [200, 429, 502],
                "why": "decision path used by probe popup",
            },
        ],
        "frontend_smoke": {
            "route": "/fields/map-center?field_id=00000000-0000-4000-8000-000000000001&index=ndvi&source=my-fields&weather=1",
            "expected_ui_contract": [
                "weather overlay module loads",
                "weather tiles request interpolation=grid",
                "probe popup fetches action recommendation",
                "task and recommendation buttons are present in popup markup",
            ],
        },
        "commands": [
            "python3 scripts/weather_runtime_smoke.py --base-url http://localhost:8000",
            "cd frontend && npm run typecheck && npm run build",
            "cd frontend && npm test -- src/components/maphub/weather/WeatherEngine.static.test.ts",
            "cd frontend && npm run e2e:weather-smoke -- --project=chromium",
        ],
    }


def _validate_time_model(time: str, model: str) -> tuple[str, str]:
    time = (time or "now").strip()
    model = (model or "best_match").strip()
    if time not in _ALLOWED_WEATHER_TIMES:
        raise HTTPException(status_code=400, detail=f"زمن غير مدعوم: {time}")
    if model not in _ALLOWED_WEATHER_MODELS:
        raise HTTPException(status_code=400, detail=f"نموذج طقس غير مدعوم: {model}")
    return time, model


def _cache_get(key: str) -> tuple[dict | None, str, int | None]:
    cached = _WEATHER_TILE_CACHE.get(key)
    if not cached:
        return None, "miss", None
    age = monotonic() - cached[0]
    if age < _WEATHER_TILE_CACHE_TTL_S:
        return cached[1], "fresh", int(age)
    if age < _WEATHER_TILE_STALE_TTL_S:
        return cached[1], "stale", int(age)
    return None, "expired", int(age)


def _cache_set(key: str, sample: dict) -> None:
    _WEATHER_TILE_CACHE[key] = (monotonic(), sample)
    if len(_WEATHER_TILE_CACHE) > 2048:
        oldest = sorted(_WEATHER_TILE_CACHE.items(), key=lambda kv: kv[1][0])[:512]
        for old_key, _ in oldest:
            _WEATHER_TILE_CACHE.pop(old_key, None)


async def _get_weather_sample_cached(
    lat: float,
    lon: float,
    time: str,
    model: str,
    key_prefix: str,
) -> tuple[dict, str, int | None, str | None]:
    """يجلب عيّنة Open‑Meteo مع cache/stale fallback موحّد.

    يوحّد منطق المرونة بين: tile-data، operation-tile، probe، ونافذة العمليات،
    حتى لا تختلف دلالة live/stale/failure بين أجزاء الخريطة.
    """
    key = f"{key_prefix}:{round(lat, 5)}:{round(lon, 5)}:{time}:{model}"
    sample, cache_state, cache_age_s = await _cache_get_async(key)
    upstream_error = None
    if cache_state == "fresh" and sample is not None:
        return sample, cache_state, cache_age_s, upstream_error
    try:
        from api.connectors.openmeteo import fetch_weather_tile_data

        sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
        await _cache_set_async(key, sample)
        return sample, "refreshed", 0, None
    except Exception as e:
        upstream_error = str(e)
        stale_sample, stale_state, stale_age = await _cache_get_async(key)
        if stale_sample is None or stale_state not in {"stale", "fresh"}:
            raise
        return stale_sample, "stale_fallback", stale_age, upstream_error


def _parse_series_hours(hours: str, max_hours: int = 72, max_frames: int = 16) -> list[int]:
    offsets: list[int] = []
    for raw in (hours or "").split(","):
        try:
            offsets.append(max(0, min(max_hours, int(raw.strip()))))
        except ValueError:
            continue
    if not offsets:
        offsets = [0, 1, 3, 6, 12, 24]
    # de-duplicate while preserving order, then limit frames.
    deduped = list(dict.fromkeys(offsets))
    return deduped[:max_frames]


def _time_key_from_hour(hour: int) -> str:
    return "now" if hour == 0 else f"+{hour}h"


def _operation_advice_ar(decision: dict) -> str:
    op = decision.get("operation")
    suitability = decision.get("suitability")
    if op == "spraying":
        if suitability in {"optimal", "acceptable"}:
            return "نافذة رش قابلة للتنفيذ مع الالتزام بالملصق وإجراءات السلامة."
        return "تأجيل الرش أفضل حتى تتحسن الرياح/الرطوبة/المطر."
    if op == "irrigation":
        if (decision.get("score") or 0) >= 0.6:
            return "أولوية ري مرتفعة؛ راجع رطوبة التربة ومرحلة النمو قبل التنفيذ."
        return "لا تظهر أولوية ري عالية في هذه النافذة."
    if op == "harvesting":
        if suitability in {"optimal", "acceptable"}:
            return "نافذة حصاد مناسبة نسبياً؛ راقب الرطوبة والمطر."
        return "الظروف غير مثالية للحصاد؛ الرطوبة/المطر/الرياح قد تؤثر على الجودة."
    if op == "sowing":
        if suitability in {"optimal", "acceptable"}:
            return "نافذة بذار مقبولة من ناحية حرارة ورطوبة التربة."
        return "تأجيل البذار قد يكون أفضل حتى تتحسن حرارة/رطوبة التربة."
    return "قرار تشغيلي تقديري من بيانات الطقس."


def _operation_priority(decision: dict) -> int:
    """أولوية تشغيلية 0..100 للعرض في لوحة القرار.

    ليست كل العمليات بنفس الدلالة: ارتفاع score في الري يعني حاجة أعلى،
    بينما في الرش/الحصاد/البذار يعني صلاحية أعلى. نحافظ على مقياس موحد
    يساعد الواجهة على ترتيب ما يجب فعله الآن.
    """
    score = float(decision.get("score") or 0.0)
    op = decision.get("operation")
    if op == "irrigation":
        # الري في خطة العمليات هو "حاجة" وليس مجرد صلاحية؛ نرفعه قليلاً عندما
        # تصل الحاجة إلى نطاق فعلي حتى لا يطغى رشٌ مثالي على إجهاد مائي واضح.
        base = round(score * 100)
        return min(100, base + 12 if score >= 0.60 else base)
    if decision.get("suitability") in {"optimal", "acceptable"}:
        return round(score * 100)
    return 0


def _task_type_for_operation(operation: str) -> str:
    return {
        "spraying": "spraying",
        "irrigation": "irrigation",
        "harvesting": "harvest",
        "sowing": "sowing",
    }.get(operation, operation)


def _task_priority_from_score(score_0_100: int) -> int:
    # field_tasks priority is ascending: 1 is highest, 5 is routine.
    if score_0_100 >= 85:
        return 1
    if score_0_100 >= 70:
        return 2
    if score_0_100 >= 50:
        return 3
    if score_0_100 >= 30:
        return 4
    return 5


def _recommended_date_from_frame(frame: dict | None) -> str:
    hour_offset = int((frame or {}).get("hour_offset") or 0)
    return (datetime.now(UTC) + timedelta(hours=hour_offset)).date().isoformat()


def _duration_for_operation(operation: str) -> int:
    return {"spraying": 120, "irrigation": 180, "harvesting": 240, "sowing": 180}.get(operation, 90)


def _build_weather_task_draft(
    field_id: str, plan_item: dict, extra_notes: str | None = None
) -> dict:
    operation = str(plan_item.get("operation") or "spraying")
    best = plan_item.get("best") or {}
    decision = best.get("operation") or {
        "operation": operation,
        "score": 0,
        "suitability": "unsafe",
    }
    priority_score = int(plan_item.get("priority") or _operation_priority(decision))
    factors = ", ".join(decision.get("limiting_factors") or []) or "لا توجد عوامل مانعة حادة"
    notes = (
        f"خطة مولّدة من Weather Operation Plan. العملية: {_operation_label_ar(operation)}. "
        f"أفضل نافذة: {best.get('time', 'now')}. الدرجة: {priority_score}%. "
        f"الحالة: {_plan_status_ar(decision)}. العوامل: {factors}. "
        f"النصيحة: {plan_item.get('advice_ar') or _operation_advice_ar(decision)}"
    )
    if extra_notes:
        notes = f"{notes}\nملاحظة المستخدم: {extra_notes}"
    return {
        "field_id": field_id,
        "task_type": _task_type_for_operation(operation),
        "operation": operation,
        "priority": _task_priority_from_score(priority_score),
        "priority_score": priority_score,
        "status": "pending",
        "recommended_date": _recommended_date_from_frame(best),
        "estimated_duration_min": _duration_for_operation(operation),
        "estimated_cost_usd": None,
        "assigned_to": None,
        "notes": notes,
        "source_event_type": "WEATHER_OPERATION_PLAN",
        "source_agent": "weather-engine",
        "decision": decision,
    }


def _weather_decision_why_ar(
    operation: str, best: dict, decision: dict, priority_score: int
) -> str:
    """يبني جملة «لماذا» عربيّة تشرح سبب اشتقاق القرار من الطقس — للخطّ الزمني للحقل.

    تلخّص: العملية + أفضل نافذة زمنية + الدرجة/الصلاحية + العوامل المانعة، حتى يرى
    المستخدم لاحقاً *لماذا* أُنشئت هذه المهمّة/التوصية (نافذة الطقس + درجة العملية).
    """
    factors = ", ".join(decision.get("limiting_factors") or []) or "لا توجد عوامل مانعة حادة"
    return (
        f"قرار مشتقّ من محرّك الطقس (Weather Operation Plan). "
        f"العملية: {_operation_label_ar(operation)}. "
        f"أفضل نافذة: {best.get('time', 'now')}. "
        f"الدرجة: {priority_score}% ({_plan_status_ar(decision)}). "
        f"العوامل: {factors}."
    )


def _build_weather_decision_record(
    field_id: str,
    plan_item: dict,
    *,
    model: str | None = None,
    target: str = "task",
) -> dict:
    """يبني صفّ decision_record من عنصر خطّة طقس — نقيّ (بلا قاعدة)، قابل للاختبار.

    يُدام في جدول decision_record (v78) القائم — رأس سلسلة النَّسَب للحقل — فيظهر تلقائيّاً
    في الخطّ الزمني للحقل عبر GET /api/v1/field/{field_id}/lineage. لا جدول/هجرة جديدة:
    decision_type نصّ حرّ (VARCHAR 60) وdecision_value هو JSONB حرّ يلتقط كامل المبرّر.

    target ∈ {"task", "recommendation"} — يميّز إن نتج القرار عن إنشاء مهمّة أو حفظ توصية.
    confidence = درجة الصلاحية (0..1) كما حسبها محرّك العمليّات (وإلا None — لا تلفيق).
    """
    operation = str(plan_item.get("operation") or "spraying")
    best = plan_item.get("best") or {}
    decision = best.get("operation") or {
        "operation": operation,
        "score": 0,
        "suitability": "unsafe",
    }
    priority_score = int(plan_item.get("priority") or _operation_priority(decision))
    score = decision.get("score")
    why_ar = _weather_decision_why_ar(operation, best, decision, priority_score)
    decision_value = {
        "decision_kind": "weather_operation_plan",
        "target": target,
        "operation": operation,
        "operation_label_ar": _operation_label_ar(operation),
        "best_window": best.get("time"),
        "best_weather_time": best.get("weather_time"),
        "score": score,
        "suitability": decision.get("suitability"),
        "priority_score": priority_score,
        "status_ar": _plan_status_ar(decision),
        "limiting_factors": decision.get("limiting_factors") or [],
        "advice_ar": plan_item.get("advice_ar") or _operation_advice_ar(decision),
        "why_ar": why_ar,
        "model": model,
        "source": "weather_operation_plan",
        "rendered_by": "weather-engine",
    }
    return {
        "field_id": field_id,
        "decision_type": "weather_operation_plan",
        "decision_value": decision_value,
        "confidence": float(score) if isinstance(score, (int, float)) else None,
        "why_ar": why_ar,
    }


async def _persist_weather_decision_record(conn, user, record: dict) -> str | None:
    """يُدِيم صفّ القرار المشتقّ من الطقس في decision_record ضمن **نفس** معاملة المستأجِر.

    يعكس حرفيّاً نمط routers/decision_record.py: INSERT في decision_record (RLS عبر
    tenant_connection) + حدث DECISION_RECORDED عبر outbox داخل نفس المعاملة. يُربَط
    بالحقل عبر field_id فيظهر في الخطّ الزمني للحقل (GET …/field/{id}/lineage).

    يُستدعى فقط حين يوجد field_id (لا قرار حقل بلا حقل). يُرجِع decision_id المُدام.
    لا يكتب جدولاً جديداً ولا يتطلّب هجرة — يعيد استخدام decision_record (v78).
    """
    if not record.get("field_id"):
        return None
    import json as _json
    from uuid import uuid4 as _uuid4

    from api.main import _emit_domain_event

    decision_id = f"weather-{_uuid4().hex[:16]}"
    await conn.execute(
        """INSERT INTO decision_record
            (decision_id, tenant_id, field_id, decision_type, region,
             stage, decision_value, confidence, created_by)
           VALUES ($1, $2::uuid, $3, $4, NULL, 'decision', $5::jsonb, $6, $7)
           ON CONFLICT (decision_id) DO NOTHING""",
        decision_id,
        str(user.tenant_id),
        record["field_id"],
        record["decision_type"],
        _json.dumps(record["decision_value"], ensure_ascii=False, default=str),
        record["confidence"],
        str(user.user_id),
    )
    await _emit_domain_event(
        conn,
        user,
        "DECISION_RECORDED",
        "decision_record",
        decision_id,
        {
            "decision_type": record["decision_type"],
            "field_id": record["field_id"],
            "source": "weather_operation_plan",
            "confidence": record["confidence"],
        },
    )
    return decision_id


def _recommendation_payload_from_plan(field_id: str, plan: dict, crop: str | None = None) -> dict:
    top = plan.get("top_recommendation") or {}
    op = top.get("operation") or "weather"
    best = top.get("best") or {}
    decision = best.get("operation") or {}
    return {
        "field_id": field_id,
        "crop": crop,
        "recommendation_type": "weather_operation_plan",
        "title_ar": f"توصية طقس تشغيلية: {_operation_label_ar(op)}",
        "reason_ar": top.get("advice_ar") or _operation_advice_ar({"operation": op, **decision}),
        "priority": top.get("priority", 0),
        "recommended_operation": op,
        "recommended_time": best.get("time"),
        "suitability": decision.get("suitability"),
        "score": decision.get("score"),
        "alerts_ar": plan.get("alerts_ar") or [],
        "provenance": {
            "source": "open-meteo+sahool-operation-plan",
            "model": plan.get("model"),
            "hours": plan.get("hours"),
            "partial": plan.get("partial"),
        },
    }


def _operation_label_ar(operation: str) -> str:
    return {
        "spraying": "الرش",
        "irrigation": "الري",
        "harvesting": "الحصاد",
        "sowing": "البذار",
    }.get(operation, operation)


def _plan_status_ar(decision: dict) -> str:
    op = decision.get("operation")
    suitability = decision.get("suitability")
    score = float(decision.get("score") or 0.0)
    if op == "irrigation":
        if score >= 0.75:
            return "أولوية ري عالية"
        if score >= 0.60:
            return "أولوية ري متوسطة"
        return "لا توجد أولوية ري واضحة"
    if suitability == "optimal":
        return "مناسب جداً"
    if suitability == "acceptable":
        return "مقبول مع احتياط"
    if suitability == "poor":
        return "ضعيف"
    return "غير آمن"


def _sample_alerts_ar(sample: dict) -> list[str]:
    alerts: list[str] = []
    if (_num(sample, "wind_speed_10m_kmh", 0) or 0) > 18:
        alerts.append("رياح مرتفعة قد تمنع الرش وتؤثر على الانجراف.")
    if (_num(sample, "wind_gusts_10m_kmh", 0) or 0) > 29:
        alerts.append("هبات الرياح مرتفعة؛ تجنب الرش والعمليات الحساسة.")
    if (_num(sample, "vapour_pressure_deficit_kpa", 0) or 0) > 2.2:
        alerts.append("VPD مرتفع؛ راقب الإجهاد المائي وجدولة الري.")
    if (_num(sample, "precipitation_mm", 0) or 0) > 0.1:
        alerts.append("هطول موجود/متوقع؛ راجع الرش والحصاد والري.")
    if (_num(sample, "temperature_2m_c", 25) or 25) > 36:
        alerts.append("حرارة مرتفعة؛ تجنب العمليات المجهدة وقت الذروة.")
    return alerts


def _parse_operations_csv(raw: str) -> list[str]:
    allowed = {"spraying", "irrigation", "harvesting", "sowing"}
    ops = [o.strip() for o in (raw or "").split(",") if o.strip()]
    if not ops:
        return ["spraying", "irrigation", "harvesting", "sowing"]
    bad = [o for o in ops if o not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"عمليات غير مدعومة: {', '.join(bad)}")
    return list(dict.fromkeys(ops))


def _best_operation_frame(frames: list[dict]) -> dict | None:
    if not frames:
        return None
    return max(frames, key=lambda f: f.get("operation", {}).get("score") or 0)


def _tile_lon(x: int, z: int) -> float:
    return x / (2**z) * 360.0 - 180.0


def _tile_lat(y: int, z: int) -> float:
    n = pi - 2.0 * pi * y / (2**z)
    return degrees(atan(sinh(n)))


def _tile_center(z: int, x: int, y: int) -> tuple[float, float]:
    west = _tile_lon(x, z)
    east = _tile_lon(x + 1, z)
    north = _tile_lat(y, z)
    south = _tile_lat(y + 1, z)
    return ((north + south) / 2.0, (west + east) / 2.0)


def _safe_layer_value(layer: str, sample: dict):
    if layer == "temperature":
        return sample.get("temperature_2m_c")
    if layer == "wind":
        return sample.get("wind_speed_10m_kmh")
    if layer == "precipitation":
        return sample.get("precipitation_mm")
    if layer == "et0":
        return sample.get("et0_fao_evapotranspiration_mm")
    if layer == "vpd":
        return sample.get("vapour_pressure_deficit_kpa")
    if layer == "soil_temperature":
        return sample.get("soil_temperature_6cm_c") or sample.get("soil_temperature_0cm_c")
    if layer == "soil_temperature_10_40cm":
        return _soil_temperature_10_40cm_value(sample)
    if layer == "spraying_drift_risk":
        return _spraying_drift_risk_value(sample)
    if layer == "soil_trafficability":
        return _soil_trafficability_value(sample)
    if layer == "heat_stress":
        return _heat_stress_value(sample)
    if layer == "disease_late_blight":
        return _disease_late_blight_value(sample)
    if layer == "disease_downy_mildew":
        return _disease_downy_mildew_value(sample)
    if layer == "disease_stripe_rust":
        return _disease_stripe_rust_value(sample)
    if layer == "soil_moisture":
        return sample.get("soil_moisture_1_to_3cm_m3m3") or sample.get(
            "soil_moisture_0_to_1cm_m3m3"
        )
    if layer == "pressure":
        return sample.get("pressure_msl_hpa")
    if layer == "clouds":
        return sample.get("cloud_cover_pct")
    return sample.get("temperature_2m_c")


def _soil_temperature_10_40cm_value(sample: dict) -> float | None:
    """Return the 10-40 cm down soil temperature approximation.

    Prefer a connector-computed value, then derive it from Open-Meteo 18/54 cm
    depths. Falls back to 6 cm only when deeper data is absent.
    """
    direct = _num(sample, "soil_temperature_10_40cm_c", None)
    if direct is not None:
        return direct
    t18 = _num(sample, "soil_temperature_18cm_c", None)
    t54 = _num(sample, "soil_temperature_54cm_c", None)
    t6 = _num(sample, "soil_temperature_6cm_c", None)
    vals: list[tuple[float, float]] = []
    if t18 is not None:
        vals.append((t18, 0.65))
    if t54 is not None:
        t40 = (t18 + (t54 - t18) * ((40 - 18) / (54 - 18))) if t18 is not None else t54
        vals.append((t40, 0.35))
    elif t6 is not None:
        vals.append((t6, 0.20))
    if not vals:
        return None
    total = sum(w for _, w in vals)
    return round(sum(v * w for v, w in vals) / total, 2)


def _spraying_drift_risk_value(sample: dict) -> float | None:
    """Derived spray-drift risk index 0..1 (higher = riskier to spray).

    Combines the three dominant drift/efficacy drivers for foliar spraying:
      - wind speed (km/h): negligible below 6, full risk by 22 (ASABE/UK LERAP
        style window — light wind is ideal, calm <2 risks inversion, strong
        >18 risks off-target drift).
      - wind gusts (km/h): gust spikes break the boom pattern; negligible below
        15, full risk by 35.
      - vapour pressure deficit (kPa): very dry air (>3.5 kPa) accelerates fine
        droplet evaporation and volatilisation; negligible below 1.2.
    Active rain (>0.1 mm) wash-off forces the index to 1.0 (do-not-spray).
    Returns None only when none of the contributing fields are present.
    """
    wind = _num(sample, "wind_speed_10m_kmh", None)
    gust = _num(sample, "wind_gusts_10m_kmh", None)
    vpd = _num(sample, "vapour_pressure_deficit_kpa", None)
    rain = _num(sample, "precipitation_mm", None)
    if wind is None and gust is None and vpd is None:
        return None
    if rain is not None and rain > 0.1:
        return 1.0
    parts: list[tuple[float, float]] = []
    if wind is not None:
        parts.append((_ramp(wind, 6.0, 22.0), 0.50))
    if gust is not None:
        parts.append((_ramp(gust, 15.0, 35.0), 0.30))
    if vpd is not None:
        parts.append((_ramp(vpd, 1.2, 3.5), 0.20))
    total = sum(w for _, w in parts)
    if total <= 0:
        return None
    return round(min(1.0, sum(v * w for v, w in parts) / total), 3)


def _soil_trafficability_value(sample: dict) -> float | None:
    """Derived soil trafficability index 0..1 (higher = safer to drive on).

    Field machinery causes compaction/rutting when the topsoil is near or above
    field capacity. The index maps near-surface volumetric soil moisture to a
    go/no-go score (1 = firm and trafficable, 0 = saturated):
      - >=0.40 m³/m³ (≈ saturation for most soils): score 0.
      - <=0.22 m³/m³ (drier than field capacity): score 1.
      - linear in between.
    A wet topsoil from very recent rain (>5 mm) caps the score at 0.5 because
    the surface stays slick even if the profile reading lags. Returns None when
    no soil-moisture reading is available.
    """
    soil_m = _num(sample, "soil_moisture_1_to_3cm_m3m3", None)
    if soil_m is None:
        soil_m = _num(sample, "soil_moisture_0_to_1cm_m3m3", None)
    if soil_m is None:
        return None
    score = 1.0 - _ramp(soil_m, 0.22, 0.40)
    rain = _num(sample, "precipitation_mm", None)
    if rain is not None and rain > 5.0:
        score = min(score, 0.5)
    return round(max(0.0, min(1.0, score)), 3)


def _heat_stress_value(sample: dict) -> float | None:
    """Derived crop/livestock heat-stress index 0..1 (higher = more stress).

    Uses a humidity-aware heat index rather than dry-bulb temperature alone, so
    humid heat reads hotter than the same temperature in dry air:
      - air temperature (°C): negligible below 28, severe by 42.
      - relative humidity (%) above 60 adds up to +0.25 to the temperature
        ramp (humid heat impairs transpirational cooling).
    The combined value is clamped to 0..1. Returns None when temperature is
    absent.
    """
    temp = _num(sample, "temperature_2m_c", None)
    if temp is None:
        return None
    rh = _num(sample, "relative_humidity_2m_pct", None)
    base = _ramp(temp, 28.0, 42.0)
    humidity_boost = 0.0
    if rh is not None and rh > 60.0:
        humidity_boost = _ramp(rh, 60.0, 100.0) * 0.25
    return round(max(0.0, min(1.0, base + humidity_boost)), 3)


def _temp_band(temp: float, lo_off: float, lo_on: float, hi_on: float, hi_off: float) -> float:
    """0..1 plateau band: 0 below ``lo_off``, ramps up to 1 across [lo_off,lo_on],
    holds 1 across [lo_on,hi_on], ramps down to 0 across [hi_on,hi_off]."""
    return min(_ramp(temp, lo_off, lo_on), 1.0 - _ramp(temp, hi_on, hi_off))


def _disease_late_blight_value(sample: dict) -> float | None:
    """Potato late blight (Phytophthora infestans) infection-window proxy 0..1.

    Epidemiological basis: Smith period / Hutton criteria — late blight is
    favoured by moderate-cool temperature (≈10-24°C, optimum ~18°C) combined
    with prolonged high humidity (RH ≥ ~90% / low VPD) and surface wetness.
    Drivers combined here (per timestep):
      - temperature band: 0 outside ≈10-24°C, full inside 14-20°C (optimum ~18°C).
      - humidity: negligible below 88% RH, full by 96% (proxy for the ≥6h RH≥90%
        wetness requirement); when RH absent, low VPD (≤0.4 kPa) substitutes.
      - wetness boost: any precipitation (>0.1 mm) adds free leaf moisture.
    Risk = temp_band * (0.7*humidity + 0.3*wetness), so a wrong temperature band
    suppresses the index even when wet (multiplicative gate).

    HONEST LIMITATION: this is a single-timestep proxy, NOT a full multi-day
    infection model. The real Smith/Hutton rules require TWO consecutive days
    each meeting min-temp ≥10°C plus ≥6h of RH≥90%; this layer approximates the
    instantaneous favourability only and cannot track infection-period duration.
    Returns None when temperature is absent (the essential gating input).
    """
    temp = _num(sample, "temperature_2m_c", None)
    if temp is None:
        return None
    rh = _num(sample, "relative_humidity_2m_pct", None)
    vpd = _num(sample, "vapour_pressure_deficit_kpa", None)
    rain = _num(sample, "precipitation_mm", None)
    if rh is None and vpd is None:
        return None
    band = _temp_band(temp, 10.0, 14.0, 20.0, 24.0)
    if rh is not None:
        humidity = _ramp(rh, 88.0, 96.0)
    else:
        humidity = 1.0 - _ramp(vpd, 0.1, 0.6)
    wetness = 1.0 if (rain is not None and rain > 0.1) else 0.0
    moisture = 0.7 * humidity + 0.3 * wetness
    return round(max(0.0, min(1.0, band * moisture)), 3)


def _disease_downy_mildew_value(sample: dict) -> float | None:
    """Grape downy mildew (Plasmopara viticola) infection-window proxy 0..1.

    Epidemiological basis: the "3-10 rule" + warm wet nights — primary infection
    needs warm humid conditions (≈18-25°C) plus free moisture from recent rain
    (≈≥10 mm) and persistent high RH. Drivers combined here (per timestep):
      - temperature band: 0 outside ≈13-30°C, full inside 18-25°C.
      - free moisture from rain: negligible below 2 mm, full by 10 mm (the
        ≈10 mm rain trigger of the 3-10 rule).
      - high RH: negligible below 80%, full by 95% (warm wet night proxy).
    Risk = temp_band * max(rain_moisture, 0.6*humidity): rain is the dominant
    trigger, but a saturated humid night alone still gives partial risk.

    HONEST LIMITATION: this is a single-timestep proxy, NOT a full multi-day
    infection model. The 3-10 rule needs ≥10°C, shoots ≥10 cm and ≥10 mm rain
    over a period plus an incubation window driven by accumulated wetness hours;
    this layer captures only the instantaneous favourability of one sample.
    Returns None when temperature is absent (the essential gating input).
    """
    temp = _num(sample, "temperature_2m_c", None)
    if temp is None:
        return None
    rh = _num(sample, "relative_humidity_2m_pct", None)
    rain = _num(sample, "precipitation_mm", None)
    if rh is None and rain is None:
        return None
    band = _temp_band(temp, 13.0, 18.0, 25.0, 30.0)
    rain_moisture = _ramp(rain, 2.0, 10.0) if rain is not None else 0.0
    humidity = _ramp(rh, 80.0, 95.0) if rh is not None else 0.0
    moisture = max(rain_moisture, 0.6 * humidity)
    return round(max(0.0, min(1.0, band * moisture)), 3)


def _disease_stripe_rust_value(sample: dict) -> float | None:
    """Wheat stripe (yellow) rust (Puccinia striiformis) infection proxy 0..1.

    Epidemiological basis: stripe rust is favoured by cool temperatures
    (≈7-15°C optimum, sporulation suppressed above ~22°C) together with extended
    leaf wetness / dew from high RH and low VPD. Drivers combined here:
      - temperature band: 0 outside ≈2-22°C, full inside 7-13°C; suppressed hard
        above 22°C (heat is lethal to the urediniospore cycle).
      - leaf wetness / dew: negligible below 85% RH, full by 95%; when RH absent,
        low VPD (≤0.3 kPa, dew-point proximity) substitutes.
    Risk = temp_band * wetness (multiplicative — cool air without dew, or dew
    without cool air, both suppress the index).

    HONEST LIMITATION: this is a single-timestep proxy, NOT a full multi-day
    infection model. Real stripe-rust epidemics depend on continuous dew-period
    duration (≥3h of leaf wetness) and day/night cycles across the latent period;
    this layer approximates instantaneous favourability of one sample only.
    Returns None when temperature is absent (the essential gating input).
    """
    temp = _num(sample, "temperature_2m_c", None)
    if temp is None:
        return None
    rh = _num(sample, "relative_humidity_2m_pct", None)
    vpd = _num(sample, "vapour_pressure_deficit_kpa", None)
    if rh is None and vpd is None:
        return None
    band = _temp_band(temp, 2.0, 7.0, 13.0, 22.0)
    if rh is not None:
        wetness = _ramp(rh, 85.0, 95.0)
    else:
        wetness = 1.0 - _ramp(vpd, 0.1, 0.5)
    return round(max(0.0, min(1.0, band * wetness)), 3)


def _ramp(value: float, low: float, high: float) -> float:
    """Linear 0..1 ramp: 0 at/below ``low``, 1 at/above ``high``."""
    if high <= low:
        return 1.0 if value >= high else 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _num(sample: dict, key: str, default: float | None = None) -> float | None:
    value = sample.get(key)
    return value if isinstance(value, (int, float)) else default


def _operation_suitability(sample: dict, operation: str) -> dict:
    """خريطة صلاحية عمليات زراعية من بيانات Open-Meteo لنقطة/بلاطة.

    الهدف هنا ليس نموذجاً زراعياً نهائياً، بل طبقة قرار عملية قابلة للرسم:
    score 0..1 + عوامل مانعة واضحة. تستخدم عتبات محافظة متوافقة مع منطق
    Weather Intelligence Layer في SAHOOL.
    """
    temp = _num(sample, "temperature_2m_c", 25.0) or 25.0
    rh = _num(sample, "relative_humidity_2m_pct", 55.0) or 55.0
    wind = _num(sample, "wind_speed_10m_kmh", 0.0) or 0.0
    gust = _num(sample, "wind_gusts_10m_kmh", wind) or wind
    rain = _num(sample, "precipitation_mm", 0.0) or 0.0
    vpd = _num(sample, "vapour_pressure_deficit_kpa", 1.5) or 1.5
    soil_m = _num(sample, "soil_moisture_1_to_3cm_m3m3", None)
    soil_t = _num(sample, "soil_temperature_6cm_c", temp) or temp

    score = 1.0
    factors: list[str] = []

    def penalize(condition: bool, amount: float, code: str):
        nonlocal score
        if condition:
            score -= amount
            factors.append(code)

    if operation == "spraying":
        penalize(wind > 18, 0.40, "wind_speed_high")
        penalize(gust > 29, 0.25, "wind_gust_high")
        penalize(temp < 5 or temp > 30, 0.25, "temperature_outside_spray_window")
        penalize(rh > 85, 0.18, "humidity_high")
        penalize(rain > 0.1, 0.40, "precipitation_present")
    elif operation == "harvesting":
        penalize(wind > 36, 0.25, "wind_high")
        penalize(rh > 70, 0.30, "humidity_high")
        penalize(rain > 0.1, 0.45, "precipitation_present")
        penalize(soil_m is not None and soil_m > 0.34, 0.22, "soil_too_wet")
    elif operation == "sowing":
        penalize(soil_t < 8 or soil_t > 35, 0.35, "soil_temperature_unsuitable")
        penalize(soil_m is not None and soil_m < 0.18, 0.22, "soil_moisture_low")
        penalize(rain > 10, 0.20, "heavy_rain_risk")
    elif operation == "irrigation":
        # للري: score أعلى عندما يكون VPD مرتفعاً/رطوبة التربة منخفضة ولا يوجد مطر.
        score = 0.45
        if vpd > 2.2:
            score += 0.22
            factors.append("high_vpd_irrigation_need")
        if soil_m is not None and soil_m < 0.20:
            score += 0.25
            factors.append("soil_moisture_low")
        if rain > 2:
            score -= 0.35
            factors.append("rain_reduces_irrigation_need")
    else:
        raise HTTPException(status_code=400, detail=f"عملية غير مدعومة: {operation}")

    score = max(0.0, min(1.0, score))
    suitability = (
        "optimal"
        if score >= 0.80
        else "acceptable"
        if score >= 0.60
        else "poor"
        if score >= 0.35
        else "unsafe"
    )
    return {
        "operation": operation,
        "score": round(score, 3),
        "suitability": suitability,
        "limiting_factors": factors,
    }


_ALLOWED_WEATHER_TILE_LAYERS = {
    "temperature",
    "wind",
    "precipitation",
    "et0",
    "vpd",
    "soil_temperature",
    "soil_temperature_10_40cm",
    "spraying_drift_risk",
    "soil_trafficability",
    "heat_stress",
    "disease_late_blight",
    "disease_downy_mildew",
    "disease_stripe_rust",
    "soil_moisture",
    "pressure",
    "clouds",
}


@router.get("/api/v1/weather/health")
def weather_health():
    """مسبار صحّة لطبقة الطقس الموحّدة (منطق محلّيّ فقط، بلا استدعاء خارجيّ).

    يؤكّد أنّ راوتر الطقس مُركَّب ويكشف حالة قاطع Open-Meteo دون استدعاء المزوّد.
    nginx /api/weather/health يُوجَّه هنا فلا تضرب واجهات فحص الخدمات جذع weather-service.
    """
    from api.connectors.openmeteo import openmeteo_breaker_state

    return {
        "status": "ok",
        "service": "weather",
        "provider": "open-meteo",
        "mode": "platform",
        "breaker": openmeteo_breaker_state(),
    }


@router.get("/api/v1/weather/readyz")
def weather_readyz(response: Response):
    """Readiness probe for production routing and Kubernetes/Docker checks.

    لا يستدعي Open‑Meteo حتى لا يتحول readiness إلى فحص شبكة خارجي. يرجع 200
    عند الجاهزية و503 عند فشل الفحوصات المحلية أو فتح القاطع.
    """
    readiness = _weather_runtime_readiness()
    if readiness["status"] != "ready":
        response.status_code = 503
    _record_weather_observation("readyz", cache_state=readiness["status"])
    return readiness


@router.get("/api/v1/weather/self-test")
def weather_self_test(response: Response):
    """Dry-run self-test for the weather engine without external I/O."""
    result = _weather_engine_self_checks()
    if result["status"] != "ok":
        response.status_code = 500
    _record_weather_observation("self-test", cache_state=result["status"])
    return result


@router.get("/api/v1/weather/wind-source-selftest")
async def weather_wind_source_selftest(
    response: Response,
    lat: float = Query(15.35, ge=-90, le=90),
    lon: float = Query(44.21, ge=-180, le=180),
    _: None = Depends(_require_service_token),
):
    """فحص **حيّ** (external I/O) لمصدرَي اتّجاه الرياح — يُشغَّل في بيئة النشر لا في CI.

    يُمرّر عبر خطّ الأنابيب الفعليّ (Open-Meteo أساسيّ ⇐ MET Norway احتياطيّ) ويُجري
    مسباراً مستقلّاً لـMET.no، فيؤكّد الاتّصال الحيّ ومصدر الاتّجاه فعليّاً (لا mock).
    صادق: أيّ تعذّر يُبلَّغ صراحةً؛ لا يُخزَّن سرّ. الإحداثيّات الافتراضيّة: صنعاء/اليمن.
    """
    from api.connectors import metno_wind
    from api.connectors.openmeteo import fetch_weather_tile_data

    resolved: dict = {"wind_direction_10m_deg": None, "source": None, "error": None}
    try:
        sample = await fetch_weather_tile_data(lat, lon)
        resolved["wind_direction_10m_deg"] = sample.get("wind_direction_10m_deg")
        resolved["source"] = sample.get("wind_direction_source")
    except Exception as exc:  # noqa: BLE001
        resolved["error"] = type(exc).__name__

    metno: dict = {
        "enabled": metno_wind.is_enabled(),
        "reachable": False,
        "wind_direction_deg": None,
        "error": None,
    }
    if metno["enabled"]:
        try:
            deg = await metno_wind.fetch_wind_direction_deg(lat, lon)
            metno["reachable"] = True
            metno["wind_direction_deg"] = deg
        except Exception as exc:  # noqa: BLE001
            metno["error"] = type(exc).__name__

    has_direction = resolved["wind_direction_10m_deg"] is not None
    status = "ok" if has_direction else "degraded"
    if not has_direction:
        response.status_code = 503
    return {
        "status": status,
        "coordinates": {"lat": lat, "lon": lon},
        "resolved": resolved,  # ما يستعمله النظام فعلاً + مصدره (open-meteo/met.no)
        "open_meteo": {
            "is_primary": True,
            "provided_direction": resolved["source"] == "open-meteo",
        },
        "met_norway": metno,  # مسبار مستقلّ للاحتياطيّ
        "note": "فحص حيّ يتطلّب وصولاً خارجيّاً (لا يُشغَّل في CI المعزول).",
    }


@router.get("/api/v1/weather/runtime-contract")
def weather_runtime_contract(response: Response, _: None = Depends(_require_service_token)):
    """UI/API runtime contract check for MapHub weather integration.

    تشخيص داخليّ (يكشف بنية النشر) ⇒ محميّ بـService Token (internal/admin فقط).
    """
    result = _weather_runtime_contract()
    if result["status"] != "ok":
        response.status_code = 500
    _record_weather_observation("runtime-contract", cache_state=result["status"])
    return result


@router.get("/api/v1/weather/env-doctor")
def weather_env_doctor(response: Response, _: None = Depends(_require_service_token)):
    """Local operational guardrail report for weather engine settings.

    يكشف متغيّرات/تهيئة البيئة ⇒ محميّ بـService Token (internal/admin فقط).
    """
    result = _weather_env_doctor()
    if result["status"] != "ok":
        response.status_code = 500
    _record_weather_observation("env-doctor", cache_state=result["status"])
    return result


@router.get("/api/v1/weather/runtime-smoke-plan")
def weather_runtime_smoke_plan():
    """Post-deploy smoke plan for operators and CI smoke jobs."""
    result = _weather_runtime_smoke_plan()
    _record_weather_observation("runtime-smoke-plan", cache_state=result["status"])
    return result


@router.get("/api/v1/weather/current", dependencies=[Depends(_rate_dependency("current"))])
async def weather_current(lat: float, lon: float):
    """الطقس الحالي من Open-Meteo. مفتوح بدون auth."""
    try:
        from api.connectors.openmeteo import describe_weather_ar, fetch_current

        data = await fetch_current(lat, lon)
        return {
            "temperature_c": data.temperature_c,
            "humidity_pct": data.humidity_pct,
            "wind_speed_ms": data.wind_speed_ms,
            "wind_direction_deg": data.wind_direction_deg,
            "wind_direction_source": data.wind_direction_source,
            "wind_gusts_ms": data.wind_gusts_ms,
            "precipitation_mm": data.precipitation_mm,
            "cloud_cover_pct": data.cloud_cover_pct,
            "weather_code": data.weather_code,
            "weather_ar": describe_weather_ar(data.weather_code),
            "is_day": data.is_day,
            "timestamp": data.timestamp,
            "source": "open-meteo",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo: {e}") from e


@router.get("/api/v1/weather/forecast", dependencies=[Depends(_rate_dependency("forecast"))])
async def weather_forecast(lat: float, lon: float, days: int = 7):
    """توقّعات ١-١٦ يوم + ET₀ (FAO-56) + spraying conditions."""
    try:
        from api.connectors.openmeteo import (
            describe_weather_ar,
            fetch_daily_forecast,
            spraying_condition_score,
        )

        forecast = await fetch_daily_forecast(lat, lon, days=days)
        return {
            "location": {"lat": lat, "lon": lon},
            "days": [
                {
                    "date": f.date,
                    "temp_max_c": f.temp_max_c,
                    "temp_min_c": f.temp_min_c,
                    "precipitation_mm": f.precipitation_mm,
                    "et0_mm": f.et0_mm,
                    "sunshine_hours": f.sunshine_hours,
                    # شمسيّ/نهاريّ — لجدولة الريّ بالطاقة الشمسيّة وتقدير الإنتاج
                    "sunrise": f.sunrise,
                    "sunset": f.sunset,
                    "daylight_hours": f.daylight_hours,
                    "solar_radiation_mj_m2": f.solar_radiation_mj_m2,
                    "wind_max_ms": f.wind_max_ms,
                    "weather_code": f.weather_code,
                    "weather_ar": describe_weather_ar(f.weather_code),
                    "spraying": (
                        lambda s: {
                            "status": s[0],
                            "reason_ar": s[1],
                        }
                    )(spraying_condition_score(f)),
                }
                for f in forecast
            ],
            "source": "open-meteo",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo: {e}") from e


@router.get("/api/v1/weather/historical", dependencies=[Depends(_rate_dependency("historical"))])
async def weather_historical(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
):
    """ERA5 reanalysis — تاريخي من ١٩٤٠. مفيد لـGDD."""
    try:
        from api.connectors.openmeteo import fetch_historical

        days = await fetch_historical(lat, lon, start_date, end_date)
        return {
            "location": {"lat": lat, "lon": lon},
            "range": {"start": start_date, "end": end_date},
            "days": [
                {
                    "date": d.date,
                    "temp_max_c": d.temp_max_c,
                    "temp_min_c": d.temp_min_c,
                    "precipitation_mm": d.precipitation_mm,
                    "et0_mm": d.et0_mm,
                }
                for d in days
            ],
            "source": "open-meteo-archive",
            "model": "ERA5",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo: {e}") from e


@router.get("/api/v1/weather/layers")
def weather_layers_manifest():
    """تعريفات طبقات الطقس/العمليات التي يرسمها SAHOOL من بيانات Open-Meteo.

    هذا manifest يجعل الواجهة لاحقاً قابلة لتوليد layer controls وlegend ديناميكياً
    بدل hardcoding كامل، مع إبقاء الرسم داخل SAHOOL.
    """
    return {
        "source": "open-meteo",
        "rendered_by": "sahool",
        "times": sorted(_ALLOWED_WEATHER_TIMES, key=lambda t: 0 if t == "now" else int(t[1:-1])),
        "models": [
            {"key": "best_match", "label_ar": "الأفضل تلقائياً"},
            {"key": "gfs_seamless", "label_ar": "GFS"},
            {"key": "ecmwf_ifs04", "label_ar": "ECMWF IFS"},
        ],
        "layers": [
            {"key": "temperature", "label_ar": "حرارة السطح", "unit": "°C", "kind": "weather"},
            {"key": "wind", "label_ar": "سرعة واتجاه الرياح", "unit": "km/h", "kind": "weather"},
            {"key": "precipitation", "label_ar": "الهطول", "unit": "mm", "kind": "weather"},
            {"key": "et0", "label_ar": "البخر-نتح المرجعي", "unit": "mm", "kind": "agro_weather"},
            {"key": "vpd", "label_ar": "عجز ضغط البخار", "unit": "kPa", "kind": "agro_weather"},
            {"key": "soil_temperature", "label_ar": "حرارة التربة", "unit": "°C", "kind": "soil"},
            {
                "key": "soil_temperature_10_40cm",
                "label_ar": "حرارة التربة 10-40 سم",
                "unit": "°C",
                "kind": "soil",
                "depth": "10-40 cm down",
                "derived": True,
                "provider_native": False,
            },
            {
                "key": "spraying_drift_risk",
                "label_ar": "خطر انجراف الرش",
                "unit": "0..1",
                "kind": "risk",
                "derived": True,
                "provider_native": False,
            },
            {
                "key": "soil_trafficability",
                "label_ar": "صلاحية مرور الآليات",
                "unit": "0..1",
                "kind": "operation",
                "derived": True,
                "provider_native": False,
            },
            {
                "key": "heat_stress",
                "label_ar": "الإجهاد الحراري",
                "unit": "0..1",
                "kind": "risk",
                "derived": True,
                "provider_native": False,
            },
            {
                "key": "disease_late_blight",
                "label_ar": "نافذة اللفحة المتأخّرة (البطاطس)",
                "unit": "0..1",
                "kind": "risk",
                "crop": "potato",
                "pathogen": "Phytophthora infestans",
                "derived": True,
                "provider_native": False,
            },
            {
                "key": "disease_downy_mildew",
                "label_ar": "نافذة البياض الزغبيّ (العنب)",
                "unit": "0..1",
                "kind": "risk",
                "crop": "grape",
                "pathogen": "Plasmopara viticola",
                "derived": True,
                "provider_native": False,
            },
            {
                "key": "disease_stripe_rust",
                "label_ar": "نافذة الصدأ المخطّط (القمح)",
                "unit": "0..1",
                "kind": "risk",
                "crop": "wheat",
                "pathogen": "Puccinia striiformis",
                "derived": True,
                "provider_native": False,
            },
            {"key": "soil_moisture", "label_ar": "رطوبة التربة", "unit": "m³/m³", "kind": "soil"},
            {"key": "pressure", "label_ar": "الضغط", "unit": "hPa", "kind": "weather"},
            {"key": "clouds", "label_ar": "الغيوم", "unit": "%", "kind": "weather"},
        ],
        "operation_layers": [
            {"key": "operation_spraying", "operation": "spraying", "label_ar": "صلاحية الرش"},
            {"key": "operation_irrigation", "operation": "irrigation", "label_ar": "أولوية الري"},
            {"key": "operation_harvesting", "operation": "harvesting", "label_ar": "صلاحية الحصاد"},
            {"key": "operation_sowing", "operation": "sowing", "label_ar": "صلاحية البذار"},
        ],
        "presets": [
            {"key": "spray_mode", "label_ar": "وضع الرش", "layer": "operation_spraying"},
            {"key": "irrigation_mode", "label_ar": "وضع الري", "layer": "operation_irrigation"},
            {"key": "harvest_mode", "label_ar": "وضع الحصاد", "layer": "operation_harvesting"},
            {"key": "sowing_mode", "label_ar": "وضع البذار", "layer": "operation_sowing"},
            {
                "key": "drift_risk_mode",
                "label_ar": "خطر انجراف الرش",
                "layer": "spraying_drift_risk",
            },
            {
                "key": "trafficability_mode",
                "label_ar": "مرور الآليات",
                "layer": "soil_trafficability",
            },
            {"key": "heat_stress_mode", "label_ar": "الإجهاد الحراري", "layer": "heat_stress"},
            {
                "key": "late_blight_mode",
                "label_ar": "نافذة اللفحة المتأخّرة",
                "layer": "disease_late_blight",
            },
            {
                "key": "downy_mildew_mode",
                "label_ar": "نافذة البياض الزغبيّ",
                "layer": "disease_downy_mildew",
            },
            {
                "key": "stripe_rust_mode",
                "label_ar": "نافذة الصدأ المخطّط",
                "layer": "disease_stripe_rust",
            },
        ],
        "cache": {
            "ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
            "stale_ttl_s": int(_WEATHER_TILE_STALE_TTL_S),
            "max_items_soft": 2048,
            "backend": _weather_cache_backend_status(),
        },
        "decision_endpoints": [
            "/api/v1/weather/probe",
            "/api/v1/weather/operation-window",
            "/api/v1/weather/operation-plan",
            "/api/v1/weather/action-recommendation",
            "/api/v1/weather/tasks/from-operation-plan",
            "/api/v1/weather/recommendations/from-operation-plan",
            "/api/v1/weather/field-weather-summary",
        ],
        "rate_limits": {
            **{
                key: {"limit": value[0], "window_s": value[1]}
                for key, value in _WEATHER_RATE_LIMITS.items()
            },
            "backend": _weather_rate_backend_status(),
            "policies": {
                key: {"limit": value[0], "window_s": value[1]}
                for key, value in _WEATHER_RATE_LIMITS.items()
            },
        },
        "tile_interpolation": {
            "supported": True,
            "modes": ["center", "grid"],
            "default_api_mode": "center",
            "frontend_mode": "grid",
            "strategy": "bilinear_2x2_center",
        },
        "observability_endpoints": [
            "/api/v1/weather/health",
            "/api/v1/weather/readyz",
            "/api/v1/weather/self-test",
            "/api/v1/weather/runtime-contract",
            "/api/v1/weather/env-doctor",
            "/api/v1/weather/runtime-smoke-plan",
            "/api/v1/weather/tile-cache/stats",
            "/api/v1/weather/tile-cache/prune",
            "/api/v1/weather/tile-cache/backend",
            "/api/v1/weather/rate-limit/backend",
            "/api/v1/weather/observability",
            "/api/v1/weather/metrics.prom",
        ],
    }


@router.get("/api/v1/weather/tile-cache/backend")
def weather_tile_cache_backend():
    """Return effective weather cache backend configuration without exposing Redis URL."""
    _record_weather_observation("tile-cache-backend", cache_state="served")
    return _weather_cache_backend_status()


@router.get("/api/v1/weather/rate-limit/backend")
def weather_rate_limit_backend():
    """Return effective weather rate-limit backend without exposing Redis URL."""
    _record_weather_observation("rate-limit-backend", cache_state="served")
    return _weather_rate_backend_status()


@router.get("/api/v1/weather/tile-cache/stats")
def weather_tile_cache_stats():
    """إحصاء خفيف لكاش بلاطات الطقس داخل sahool-platform."""
    return _weather_cache_snapshot()


@router.get("/api/v1/weather/observability")
def weather_observability():
    """مشاهدة تشغيلية خفيفة لمحرك الطقس بدون Prometheus إلزامي.

    تعرض عدادات الطلبات، حالات الكاش، أخطاء المصدر، وأكثر الطبقات/العمليات
    استخداماً. لا تحتوي على أسرار ولا تستدعي Open‑Meteo.
    """
    return {
        "service": "weather-engine",
        "source": "open-meteo",
        "rendered_by": "sahool",
        "cache": _weather_cache_snapshot(),
        "metrics": {
            "requests": _metrics_bucket("requests"),
            "cache_states": _metrics_bucket("cache_states"),
            "upstream": _metrics_bucket("upstream"),
            "layers": _metrics_bucket("layers"),
            "operations": _metrics_bucket("operations"),
            "rate_limited": _metrics_bucket("rate_limited"),
            "cache_backends": _metrics_bucket("cache_backends"),
        },
        "rate_limits": {
            "backend": _weather_rate_backend_status(),
            "policies": {
                key: {"limit": value[0], "window_s": value[1]}
                for key, value in _WEATHER_RATE_LIMITS.items()
            },
        },
    }


@router.get("/api/v1/weather/metrics.prom")
def weather_metrics_prometheus(_: None = Depends(_require_service_token)):
    """Prometheus/OpenMetrics compatible text export for the weather engine.

    لا يستدعي Open‑Meteo ولا يكشف أسراراً؛ الهدف ربط Grafana/Prometheus أو
    فحص سريع من Docker/Kubernetes بدون إضافة تبعية prometheus_client.

    كشط داخليّ (Prometheus) ⇒ محميّ بـService Token (X-Agent-Token)؛ يُمرَّر رأس
    التوكن من جامع المقاييس الداخليّ، لا يُكشَف للعموم.
    """
    return Response(
        content=_weather_metrics_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.post("/api/v1/weather/tile-cache/prune")
def weather_tile_cache_prune(
    expired_only: bool = Query(True),
    _: None = Depends(_require_service_token),
):
    """تنظيف كاش الطقس من العناصر المنتهية أو stale.

    expired_only=true يحذف ما تجاوز stale TTL فقط. عند false يحذف كل ما تجاوز
    TTL الطازج، وهو مفيد قبل اختبارات load/soak أو عند تبديل سياسة الكاش.

    نقطة *مُتلِفة* (تُفرِغ كاش البنية التحتيّة) ⇒ محميّة بـService Token (X-Agent-Token)
    كي لا يُجبر مجهول إفراغ الكاش (تضخيم طلبات Open-Meteo).
    """
    result = _prune_weather_cache(expired_only=expired_only)
    _record_weather_observation("tile-cache-prune", cache_state="served")
    return result


# وحدات طبقات الطقس (مصدر واحد) — يُستعمَل في ردّ البلاطة الناجح والمحايد.
_WEATHER_TILE_UNITS = {
    "temperature": "°C",
    "wind": "km/h",
    "precipitation": "mm",
    "et0": "mm",
    "vpd": "kPa",
    "soil_temperature": "°C",
    "soil_temperature_10_40cm": "°C",
    "spraying_drift_risk": "0..1",
    "soil_trafficability": "0..1",
    "heat_stress": "0..1",
    "disease_late_blight": "0..1",
    "disease_downy_mildew": "0..1",
    "disease_stripe_rust": "0..1",
    "soil_moisture": "m³/m³",
    "pressure": "hPa",
    "clouds": "%",
}


def _unavailable_tile_response(
    *,
    z: int,
    x: int,
    y: int,
    lat: float,
    lon: float,
    layer: str,
    time: str,
    model: str,
    upstream_error: str,
) -> dict:
    """بلاطة طقس محايدة (200) عند تعذّر Open-Meteo بلا كاش — بدل 502 الذي يُغرِق
    السجلّ ويُظهِر بلاطات مكسورة. الواجهة تُصيّر value=null كبلاطة محايدة («—» + لون
    فاتح). نُبقي cache_state=unavailable وupstream_error للرصد، وavailable=false صريحة.
    """
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": layer,
        "value": None,
        "unit": _WEATHER_TILE_UNITS.get(layer, ""),
        "sample": None,
        "time": time,
        "model": model,
        "source": "open-meteo",
        "rendered_by": "sahool-client-gridlayer",
        "cache_ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
        "cache_state": "unavailable",
        "cache_age_s": None,
        "upstream_error": upstream_error,
        "interpolation": None,
        "available": False,
    }


@router.get(
    "/api/v1/weather/tile-data/{z}/{x}/{y}", dependencies=[Depends(_rate_dependency("tile-data"))]
)
async def weather_tile_data(
    z: int,
    x: int,
    y: int,
    layer: str = Query(
        "temperature",
        description="temperature|wind|precipitation|et0|vpd|soil_temperature|soil_temperature_10_40cm|spraying_drift_risk|soil_trafficability|heat_stress|disease_late_blight|disease_downy_mildew|disease_stripe_rust|soil_moisture|pressure|clouds",
    ),
    time: str = Query("now", description="now|+1h|+3h|+6h|+12h|+24h|+48h"),
    model: str = Query("best_match", description="best_match أو نموذج Open-Meteo صريح عند الحاجة"),
    interpolation: Literal["center", "grid"] = Query(
        "center", description="center|grid — grid returns 2x2+center interpolation points"
    ),
):
    """بيانات بلاطة طقس واحدة من Open-Meteo، ترسمها SAHOOL في الواجهة.

    لا نعيد PNG جاهزة ولا نستخدم مزوّد خرائط خارجي. نحسب مركز بلاطة WebMercator،
    نجلب عيّنة Open-Meteo، ثم تعيد الواجهة رسم البلاطة كـSVG/GridLayer مع
    animation وlegend وlayer controls.
    """
    if z < 0 or z > 18:
        raise HTTPException(status_code=400, detail="z خارج النطاق 0..18")
    max_tile = 2**z
    if x < 0 or y < 0 or x >= max_tile or y >= max_tile:
        raise HTTPException(status_code=400, detail="x/y خارج نطاق البلاطات لهذا التكبير")
    if layer not in _ALLOWED_WEATHER_TILE_LAYERS:
        raise HTTPException(status_code=400, detail=f"طبقة غير مدعومة: {layer}")
    time, model = _validate_time_model(time, model)

    lat, lon = _tile_center(z, x, y)
    interpolation_payload = None
    if interpolation == "grid":
        (
            sample,
            cache_state,
            cache_age_s,
            upstream_error,
            interpolation_payload,
        ) = await _weather_tile_interpolation_payload(
            z=z, x=x, y=y, layer=layer, time=time, model=model
        )
        if sample is None:
            upstream_error = upstream_error or "interpolation failed"
            cache_state = "miss"
    else:
        key = f"{z}:{x}:{y}:{time}:{model}"
        sample, cache_state, cache_age_s = await _cache_get_async(key)
        upstream_error = None
    if interpolation != "grid" or sample is None:
        key = f"{z}:{x}:{y}:{time}:{model}"
        sample, cache_state, cache_age_s = await _cache_get_async(key)
        upstream_error = None
        if cache_state != "fresh":
            try:
                from api.connectors.openmeteo import fetch_weather_tile_data

                sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
                await _cache_set_async(key, sample)
                cache_state = "refreshed"
                cache_age_s = 0
            except Exception as e:
                upstream_error = str(e)
                # إن وجدت عينة stale، نعيدها بدل كسر الخريطة أثناء انقطاع Open‑Meteo.
                stale_sample, stale_state, stale_age = await _cache_get_async(key)
                if stale_sample is None or stale_state not in {"stale", "fresh"}:
                    # لا كاش ولا منبع ⇒ بلاطة محايدة (200) بدل 502: لا تكسر الخريطة
                    # ولا تُغرِق السجلّ بـBad Gateway لكلّ بلاطة عند انقطاع Open‑Meteo.
                    _record_weather_observation(
                        "tile-data",
                        cache_state="unavailable",
                        upstream_error=upstream_error,
                        layer=layer,
                    )
                    return _unavailable_tile_response(
                        z=z,
                        x=x,
                        y=y,
                        lat=lat,
                        lon=lon,
                        layer=layer,
                        time=time,
                        model=model,
                        upstream_error=upstream_error,
                    )
                sample = stale_sample
                cache_state = "stale_fallback"
                cache_age_s = stale_age

    _record_weather_observation(
        "tile-data", cache_state=cache_state, upstream_error=upstream_error, layer=layer
    )
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": layer,
        "value": _safe_layer_value(layer, sample),
        "unit": _WEATHER_TILE_UNITS.get(layer, ""),
        "sample": sample,
        "time": time,
        "model": model,
        "source": "open-meteo",
        "rendered_by": "sahool-client-gridlayer",
        "cache_ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
        "cache_state": cache_state,
        "cache_age_s": cache_age_s,
        "upstream_error": upstream_error,
        "interpolation": interpolation_payload,
    }


@router.get(
    "/api/v1/weather/operation-tile-data/{z}/{x}/{y}",
    dependencies=[Depends(_rate_dependency("operation-tile-data"))],
)
async def weather_operation_tile_data(
    z: int,
    x: int,
    y: int,
    operation: Literal["spraying", "harvesting", "sowing", "irrigation"] = Query("spraying"),
    time: str = Query("now"),
    model: str = Query("best_match"),
    interpolation: Literal["center", "grid"] = Query("center"),
):
    """بلاطة صلاحية عملية زراعية؛ Open-Meteo بيانات، SAHOOL قرار ورسم."""
    if z < 0 or z > 18:
        raise HTTPException(status_code=400, detail="z خارج النطاق 0..18")
    max_tile = 2**z
    if x < 0 or y < 0 or x >= max_tile or y >= max_tile:
        raise HTTPException(status_code=400, detail="x/y خارج نطاق البلاطات لهذا التكبير")
    time, model = _validate_time_model(time, model)
    lat, lon = _tile_center(z, x, y)
    interpolation_payload = None
    if interpolation == "grid":
        (
            sample,
            cache_state,
            cache_age_s,
            upstream_error,
            interpolation_payload,
        ) = await _weather_tile_interpolation_payload(
            z=z, x=x, y=y, layer="temperature", time=time, model=model, operation=operation
        )
        if sample is None:
            upstream_error = upstream_error or "operation interpolation failed"
            cache_state = "miss"
    else:
        key = f"op:{operation}:{z}:{x}:{y}:{time}:{model}"
        sample, cache_state, cache_age_s = await _cache_get_async(key)
        upstream_error = None
    if interpolation != "grid" or sample is None:
        key = f"op:{operation}:{z}:{x}:{y}:{time}:{model}"
        sample, cache_state, cache_age_s = await _cache_get_async(key)
        upstream_error = None
        if cache_state != "fresh":
            try:
                from api.connectors.openmeteo import fetch_weather_tile_data

                sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
                await _cache_set_async(key, sample)
                cache_state = "refreshed"
                cache_age_s = 0
            except Exception as e:
                upstream_error = str(e)
                stale_sample, stale_state, stale_age = await _cache_get_async(key)
                if stale_sample is None or stale_state not in {"stale", "fresh"}:
                    raise HTTPException(
                        status_code=502, detail=f"Open-Meteo operation tile-data: {e}"
                    ) from e
                sample = stale_sample
                cache_state = "stale_fallback"
                cache_age_s = stale_age
    decision = _operation_suitability(sample, operation)
    _record_weather_observation(
        "operation-tile-data",
        cache_state=cache_state,
        upstream_error=upstream_error,
        operation=operation,
        layer=f"operation_{operation}",
    )
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": f"operation_{operation}",
        "value": decision["score"],
        "unit": "score",
        "operation": decision,
        "sample": sample,
        "time": time,
        "model": model,
        "source": "open-meteo+sahool-rules",
        "rendered_by": "sahool-client-gridlayer",
        "cache_ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
        "cache_state": cache_state,
        "cache_age_s": cache_age_s,
        "upstream_error": upstream_error,
        "interpolation": interpolation_payload,
    }


@router.get("/api/v1/weather/probe", dependencies=[Depends(_rate_dependency("probe"))])
async def weather_probe(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: str = Query("now"),
    model: str = Query("best_match"),
):
    """قراءة نقطة تحت المؤشر/النقرة + قرارات زراعية مختصرة."""
    time, model = _validate_time_model(time, model)
    key = f"probe:{round(lat, 4)}:{round(lon, 4)}:{time}:{model}"
    sample, cache_state, cache_age_s = await _cache_get_async(key)
    upstream_error = None
    if cache_state != "fresh":
        try:
            from api.connectors.openmeteo import fetch_weather_tile_data

            sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
            await _cache_set_async(key, sample)
            cache_state = "refreshed"
            cache_age_s = 0
        except Exception as e:
            upstream_error = str(e)
            stale_sample, stale_state, stale_age = await _cache_get_async(key)
            if stale_sample is None or stale_state not in {"stale", "fresh"}:
                raise HTTPException(status_code=502, detail=f"Open-Meteo probe: {e}") from e
            sample = stale_sample
            cache_state = "stale_fallback"
            cache_age_s = stale_age
    operations = {
        op: _operation_suitability(sample, op)
        for op in ["spraying", "harvesting", "sowing", "irrigation"]
    }
    _record_weather_observation("probe", cache_state=cache_state, upstream_error=upstream_error)
    return {
        "location": {"lat": lat, "lon": lon},
        "time": time,
        "model": model,
        "sample": sample,
        "operations": operations,
        "source": "open-meteo+sahool-rules",
        "cache_state": cache_state,
        "cache_age_s": cache_age_s,
        "upstream_error": upstream_error,
    }


@router.get(
    "/api/v1/weather/operation-window", dependencies=[Depends(_rate_dependency("operation-window"))]
)
async def weather_operation_window(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    operation: Literal["spraying", "harvesting", "sowing", "irrigation"] = Query("spraying"),
    hours: str = Query("0,1,3,6,12,24,48"),
    model: str = Query("best_match"),
):
    """أفضل نافذة زمنية لعملية زراعية عند نقطة محددة من بيانات Open‑Meteo.

    تستخدمها الواجهة في probe popup ليعرف المستخدم ليس فقط حالة النقطة الآن،
    بل متى تصبح النافذة أفضل خلال الساعات القادمة.
    """
    _, model = _validate_time_model("now", model)
    frames: list[dict] = []
    upstream_errors: list[str] = []
    for h in _parse_series_hours(hours):
        time_key = _time_key_from_hour(h)
        try:
            sample, cache_state, cache_age_s, upstream_error = await _get_weather_sample_cached(
                lat, lon, time_key, model, f"window:{operation}"
            )
            decision = _operation_suitability(sample, operation)
            frames.append(
                {
                    "hour_offset": h,
                    "time": time_key,
                    "weather_time": sample.get("time"),
                    "operation": decision,
                    "sample": sample,
                    "cache_state": cache_state,
                    "cache_age_s": cache_age_s,
                    "upstream_error": upstream_error,
                }
            )
        except Exception as e:
            upstream_errors.append(f"{time_key}: {e}")
    if not frames:
        raise HTTPException(status_code=502, detail="Open-Meteo operation-window unavailable")
    best = _best_operation_frame(frames)
    _record_weather_observation(
        "operation-window",
        cache_state="partial" if upstream_errors else "served",
        upstream_error="; ".join(upstream_errors) if upstream_errors else None,
        operation=operation,
    )
    return {
        "location": {"lat": lat, "lon": lon},
        "operation": operation,
        "model": model,
        "frames": frames,
        "best": best,
        "advice_ar": _operation_advice_ar(best["operation"]) if best else "لا توجد نافذة موثوقة.",
        "source": "open-meteo+sahool-rules",
        "partial": bool(upstream_errors),
        "upstream_errors": upstream_errors[:6],
    }


@router.get(
    "/api/v1/weather/field-weather-summary",
    dependencies=[Depends(_rate_dependency("field-weather-summary"))],
)
async def weather_field_summary(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: str = Query("now"),
    model: str = Query("best_match"),
):
    """ملخص طقس زراعي للحقل: قراءة حالية + قرارات + أفضل نافذة عملية.

    Endpoint خفيف للوحة الحقل أو بطاقة الخريطة: يعطي نظرة تشغيلية واحدة بدلاً
    من أن تجمع الواجهة probe + operation-window لكل عملية يدوياً.
    """
    time, model = _validate_time_model(time, model)
    try:
        sample, cache_state, cache_age_s, upstream_error = await _get_weather_sample_cached(
            lat, lon, time, model, "field-summary"
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo field-weather-summary: {e}") from e
    operations = {
        op: _operation_suitability(sample, op)
        for op in ["spraying", "harvesting", "sowing", "irrigation"]
    }
    critical = _sample_alerts_ar(sample)
    _record_weather_observation(
        "field-weather-summary", cache_state=cache_state, upstream_error=upstream_error
    )
    return {
        "location": {"lat": lat, "lon": lon},
        "time": time,
        "model": model,
        "sample": sample,
        "operations": operations,
        "alerts_ar": critical,
        "cache_state": cache_state,
        "cache_age_s": cache_age_s,
        "upstream_error": upstream_error,
        "source": "open-meteo+sahool-rules",
    }


@router.get(
    "/api/v1/weather/operation-plan", dependencies=[Depends(_rate_dependency("operation-plan"))]
)
async def weather_operation_plan(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    operations: str = Query("spraying,irrigation,harvesting,sowing"),
    hours: str = Query("0,1,3,6,12,24,48"),
    model: str = Query("best_match"),
):
    """خطة عمليات طقس زراعية متعددة العمليات لنقطة/حقل واحد.

    هذه هي الطبقة التنفيذية فوق operation-window: تجمع الرش/الري/الحصاد/البذار،
    تختار أفضل نافذة لكل عملية، ثم ترتب التوصيات حتى تعرض الواجهة: ماذا أفعل الآن
    وماذا أؤجل، مع أسباب وبيانات كاش واضحة.
    """
    _, model = _validate_time_model("now", model)
    op_list = _parse_operations_csv(operations)
    hour_offsets = _parse_series_hours(hours)
    plan_items: list[dict] = []
    upstream_errors: list[str] = []
    all_alerts: list[str] = []

    for op in op_list:
        frames: list[dict] = []
        for h in hour_offsets:
            time_key = _time_key_from_hour(h)
            try:
                sample, cache_state, cache_age_s, upstream_error = await _get_weather_sample_cached(
                    lat, lon, time_key, model, f"plan:{op}"
                )
                decision = _operation_suitability(sample, op)
                if h == 0:
                    all_alerts.extend(_sample_alerts_ar(sample))
                frames.append(
                    {
                        "hour_offset": h,
                        "time": time_key,
                        "weather_time": sample.get("time"),
                        "operation": decision,
                        "status_ar": _plan_status_ar(decision),
                        "priority": _operation_priority(decision),
                        "cache_state": cache_state,
                        "cache_age_s": cache_age_s,
                        "upstream_error": upstream_error,
                    }
                )
            except Exception as e:
                upstream_errors.append(f"{op}:{time_key}: {e}")
        best = _best_operation_frame(frames)
        now_frame = next((f for f in frames if f.get("hour_offset") == 0), None)
        best_decision = best.get("operation") if best else None
        plan_items.append(
            {
                "operation": op,
                "label_ar": _operation_label_ar(op),
                "now": now_frame,
                "best": best,
                "frames": frames,
                "advice_ar": _operation_advice_ar(
                    best_decision or {"operation": op, "score": 0, "suitability": "unsafe"}
                ),
                "recommended": bool(best and _operation_priority(best.get("operation", {})) >= 60),
                "priority": _operation_priority(best.get("operation", {})) if best else 0,
            }
        )

    plan_items.sort(
        key=lambda item: (
            item.get("priority", 0),
            1 if item.get("operation") == "irrigation" and item.get("priority", 0) >= 60 else 0,
        ),
        reverse=True,
    )
    if not any(item["frames"] for item in plan_items):
        raise HTTPException(status_code=502, detail="Open-Meteo operation-plan unavailable")
    dedup_alerts = list(dict.fromkeys(all_alerts))
    top = plan_items[0] if plan_items else None
    for item in plan_items:
        _record_weather_observation(
            "operation-plan",
            cache_state="partial" if upstream_errors else "served",
            upstream_error="; ".join(upstream_errors) if upstream_errors else None,
            operation=item.get("operation"),
        )
    return {
        "location": {"lat": lat, "lon": lon},
        "model": model,
        "hours": hour_offsets,
        "operations": plan_items,
        "recommended_now": [item for item in plan_items if item.get("recommended")],
        "top_recommendation": top,
        "alerts_ar": dedup_alerts,
        "partial": bool(upstream_errors),
        "upstream_errors": upstream_errors[:10],
        "source": "open-meteo+sahool-operation-plan",
    }


@router.get(
    "/api/v1/weather/action-recommendation",
    dependencies=[Depends(_rate_dependency("weather-action-recommendation"))],
)
async def weather_action_recommendation(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    client_field_ref: str | None = Query(
        None,
        min_length=1,
        max_length=80,
        description=(
            "Opaque client-side field reference used only for draft labels. "
            "This public endpoint must not dereference it against tenant data."
        ),
    ),
    field_id: str | None = Query(
        None,
        min_length=1,
        max_length=80,
        deprecated=True,
        description="Deprecated alias for client_field_ref; not dereferenced server-side.",
    ),
    operations: str = Query("spraying,irrigation,harvesting,sowing"),
    hours: str = Query("0,1,3,6,12,24,48"),
    model: str = Query("best_match"),
):
    """توصية تشغيلية قابلة للتحويل إلى مهمة من خطة الطقس.

    هذا endpoint هو جسر المنتج بين الخريطة والمهام: يعطي أفضل توصية، ومسودة مهمة
    جاهزة، وروابط الإجراءات التالية. لا يكتب في قاعدة البيانات.

    ``client_field_ref`` و``field_id`` ليسا مفاتيح ملكية tenant هنا؛ هما
    معرفان شفافان لمسودة الواجهة فقط. أي قراءة فعلية من ``fields``/``farms``
    يجب أن تنتقل إلى endpoint authenticated.
    """
    field_ref = client_field_ref or field_id
    plan = await weather_operation_plan(
        lat=lat, lon=lon, operations=operations, hours=hours, model=model
    )
    top = plan.get("top_recommendation") or {}
    draft = _build_weather_task_draft(field_ref or "", top) if field_ref and top else None
    recommendation = _recommendation_payload_from_plan(field_ref or "", plan) if field_ref else None
    _record_weather_observation("weather-action-recommendation", cache_state="served")
    return {
        "location": {"lat": lat, "lon": lon},
        "client_field_ref": field_ref,
        "field_id": field_ref,  # backward-compatible response field; not DB-backed.
        "field_ref_is_authoritative": False,
        "operation_plan": plan,
        "recommendation": recommendation,
        "task_draft": draft,
        "actions": {
            "create_task_endpoint": "/api/v1/weather/tasks/from-operation-plan",
            "save_recommendation_endpoint": "/api/v1/weather/recommendations/from-operation-plan",
        },
        "source": "open-meteo+sahool-action-bridge",
    }


@router.get(
    "/api/v1/weather/alerts",
    dependencies=[Depends(_rate_dependency("weather-action-recommendation"))],
)
async def weather_alerts(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    model: str = Query("best_match"),
    hours: str = Query("0,1,3,6,12,24,48"),
):
    """تنبيهات طقس زراعيّة مشتقّة بإحداثيّات (عامّة، بلا بيانات مستأجِر).

    تحسب خطّة العمليّات عبر ``weather_operation_plan`` (مرآةً لنقطة action-recommendation)
    وتجلب عيّنة الآن، ثمّ تشتقّ التنبيهات عبر ``derive_weather_alerts`` (منطق نقيّ).
    لا تكتب في قاعدة البيانات ولا تقرأ حالة مستأجِر.
    """
    _, model = _validate_time_model("now", model)
    plan = await weather_operation_plan(
        lat=lat, lon=lon, operations="spraying", hours=hours, model=model
    )
    sample, _state, _age, _err = await _get_weather_sample_cached(lat, lon, "now", model, "alerts")
    alerts = derive_weather_alerts(sample, plan)
    _record_weather_observation("weather-action-recommendation", cache_state="served")

    # هذه النقطة عامّة (اشتقاق بإحداثيّات، بلا كتابة). لتحويل التنبيهات إلى إشعارات
    # حقيقيّة لحقلٍ مُعيَّن (إدراج في alerts + ALERT_CREATED ⇒ وكيل الإشعارات): استخدم
    # النقطة المُصادَقة POST /api/v1/weather/alerts/notify أدناه.

    return {
        "location": {"lat": lat, "lon": lon},
        "alerts": alerts,
        "source": "open-meteo+sahool-weather-alerts",
    }


_ALERT_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def weather_alert_rows_to_persist(derived: list[dict], min_severity: str = "warning") -> list[dict]:
    """منطق نقيّ (لا DB): يُرشّح التنبيهات المشتقّة حسب أدنى شدّة ويُحوّلها إلى صفوف
    جدول ``alerts`` (alert_type/severity/title_ar/message_ar). يُسبَق النوع بـ``weather_``
    لتجنّب تضارب أنواع التنبيهات الأخرى وتمكين منع التكرار لكلّ نوع. قابل للاختبار offline.
    """
    min_rank = _ALERT_SEVERITY_RANK.get(min_severity, 1)
    rows: list[dict] = []
    for a in derived:
        if _ALERT_SEVERITY_RANK.get(a.get("severity"), 0) < min_rank:
            continue
        rows.append(
            {
                "alert_type": f"weather_{a.get('type', 'generic')}",
                "severity": a.get("severity", "warning"),
                "title_ar": a.get("title_ar", "تنبيه طقس"),
                "message_ar": a.get("detail_ar") or a.get("title_ar", "تنبيه طقس"),
            }
        )
    return rows


class WeatherAlertsNotifyRequest(BaseModel):
    field_id: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    model: str = "best_match"
    hours: str = "0,1,3,6,12,24,48"
    min_severity: str = "warning"  # info | warning | critical
    dry_run: bool = False


@router.post(
    "/api/v1/weather/alerts/notify",
    dependencies=[Depends(_rate_dependency("weather-action-recommendation"))],
)
async def weather_alerts_notify(
    req: WeatherAlertsNotifyRequest,
    user=Depends(
        __import__("api.main", fromlist=["require_permission", "Permission"]).require_permission(
            __import__("api.main", fromlist=["Permission"]).Permission.OBSERVATION_RECORD
        )
    ),
):
    """يحوّل تنبيهات الطقس المشتقّة إلى إشعارات حقيقيّة لحقلٍ مُعيَّن.

    يشتقّ التنبيهات (derive_weather_alerts)، يُرشّحها حسب ``min_severity``، ثمّ — ضمن
    اتّصال المستأجِر (RLS، outbox) — يُدرِج كلّ تنبيه جديد في جدول ``alerts`` ويُصدِر
    ``ALERT_CREATED`` فيلتقطه وكيل الإشعارات للبثّ الحيّ — نفس مسار routers/alerts.py
    والتوليد التلقائيّ في main.py. منع تكرار لكلّ نوع (لا تنبيه نشط مكرّر). ``dry_run``
    يُعيد ما سيُنشأ بلا كتابة. مُصادَق (يكتب بيانات مستأجِر).
    """
    _, model = _validate_time_model("now", req.model)
    plan = await weather_operation_plan(
        lat=req.lat, lon=req.lon, operations="spraying", hours=req.hours, model=model
    )
    sample, _state, _age, _err = await _get_weather_sample_cached(
        req.lat, req.lon, "now", model, "alerts-notify"
    )
    derived = derive_weather_alerts(sample, plan)
    rows = weather_alert_rows_to_persist(derived, req.min_severity)

    if req.dry_run:
        _record_weather_observation("weather-alerts-notify", cache_state="dry_run")
        return {"created": False, "dry_run": True, "would_notify": rows, "alerts": derived}

    import uuid as _uuid

    from api.main import _db_unavailable, _emit_domain_event, tenant_connection

    created: list[dict] = []
    try:
        async with tenant_connection(user) as conn:
            existing = await conn.fetch(
                "SELECT alert_type FROM alerts "
                "WHERE tenant_id = $1::uuid AND field_id = $2 AND status = 'active'",
                str(user.tenant_id),
                req.field_id,
            )
            existing_types = {r["alert_type"] for r in existing}
            for row in rows:
                if row["alert_type"] in existing_types:
                    continue
                alert_id = "alr_" + _uuid.uuid4().hex[:12]
                await conn.execute(
                    """INSERT INTO alerts
                        (alert_id, tenant_id, field_id, alert_type, severity,
                         title_ar, message_ar, status)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'active')""",
                    alert_id,
                    str(user.tenant_id),
                    req.field_id,
                    row["alert_type"],
                    row["severity"],
                    row["title_ar"],
                    row["message_ar"],
                )
                await _emit_domain_event(
                    conn,
                    user,
                    "ALERT_CREATED",
                    "alert",
                    alert_id,
                    {
                        "severity": row["severity"],
                        "alert_type": row["alert_type"],
                        "field_id": req.field_id,
                        "source": "weather_alerts",
                    },
                )
                existing_types.add(row["alert_type"])
                created.append({"alert_id": alert_id, **row})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("إنشاء تنبيهات الطقس", e) from e

    _record_weather_observation("weather-alerts-notify", cache_state="served")
    return {
        "created": True,
        "notified": len(created),
        "alerts": created,
        "derived_count": len(derived),
    }


@router.post(
    "/api/v1/weather/tasks/from-operation-plan",
    dependencies=[Depends(_rate_dependency("task-from-operation-plan"))],
)
async def weather_create_task_from_operation_plan(
    req: WeatherTaskFromPlanRequest,
    user=Depends(
        __import__("api.main", fromlist=["require_permission", "Permission"]).require_permission(
            __import__("api.main", fromlist=["Permission"]).Permission.FIELD_EDIT
        )
    ),
):
    """ينشئ مهمة حقل من أفضل نافذة في Weather Operation Plan.

    dry_run=true يعيد المسودة فقط ولا يكتب في قاعدة البيانات؛ مفيد للواجهة قبل أن
    يضغط المستخدم «إنشاء مهمة».
    """
    plan = await weather_operation_plan(
        lat=req.lat,
        lon=req.lon,
        operations=req.operation,
        hours=req.hours,
        model=req.model,
    )
    top = plan.get("top_recommendation") or {}
    draft = _build_weather_task_draft(req.field_id, top, extra_notes=req.notes)
    draft["assigned_to"] = req.assigned_to
    draft["estimated_cost_usd"] = req.estimated_cost_usd
    if req.dry_run:
        _record_weather_observation(
            "task-from-operation-plan", cache_state="dry_run", operation=req.operation
        )
        return {"created": False, "dry_run": True, "task": draft, "operation_plan": plan}

    try:
        from api.main import (
            _TASK_COLS,
            _db_unavailable,
            _emit_domain_event,
            _row_to_task,
            tenant_connection,
        )

        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                f"""INSERT INTO field_tasks
                       (tenant_id, field_id, task_type, priority, status, recommended_date,
                        estimated_duration_min, estimated_cost_usd, assigned_to, notes,
                        source_event_type, source_agent)
                   VALUES ($1::uuid, $2, $3, $4, 'pending', $5::date, $6, $7, $8, $9, $10, $11)
                   RETURNING {_TASK_COLS}""",
                str(user.tenant_id),
                draft["field_id"],
                draft["task_type"],
                draft["priority"],
                draft["recommended_date"],
                draft["estimated_duration_min"],
                draft["estimated_cost_usd"],
                draft["assigned_to"],
                draft["notes"],
                draft["source_event_type"],
                draft["source_agent"],
            )
            task = _row_to_task(row).model_dump()
            await _emit_domain_event(
                conn,
                user,
                "TASK_CREATED",
                "task",
                task["task_id"],
                {
                    "field_id": req.field_id,
                    "source": "weather_operation_plan",
                    "operation": req.operation,
                },
            )
            # رابط الخطّ الزمني: نُدِيم سبب الطقس (نافذة + درجة + مصدر) في decision_record
            # ضمن **نفس** المعاملة (RLS) ليظهر «لماذا أُنشئت المهمّة» في خطّ الحقل الزمني.
            decision_record = _build_weather_decision_record(
                req.field_id, top, model=req.model, target="task"
            )
            weather_decision_id = await _persist_weather_decision_record(
                conn, user, decision_record
            )
    except Exception as e:  # noqa: BLE001
        from api.main import _db_unavailable

        raise _db_unavailable("إنشاء مهمة من خطة الطقس", e) from e
    _record_weather_observation(
        "task-from-operation-plan", cache_state="created", operation=req.operation
    )
    return {
        "created": True,
        "dry_run": False,
        "task": task,
        "weather_decision_id": weather_decision_id,
        "weather_decision_why_ar": decision_record["why_ar"],
        "operation_plan": plan,
    }


@router.post(
    "/api/v1/weather/recommendations/from-operation-plan",
    dependencies=[Depends(_rate_dependency("recommendation-from-operation-plan"))],
)
async def weather_recommendation_from_operation_plan(
    req: WeatherRecommendationFromPlanRequest,
    user=Depends(
        __import__("api.main", fromlist=["require_permission", "Permission"]).require_permission(
            __import__("api.main", fromlist=["Permission"]).Permission.RECOMMENDATION_REQUEST
        )
    ),
):
    """يحفظ توصية طقس تشغيلية في جدول recommendations أو يعيدها كـdry-run."""
    plan = await weather_operation_plan(
        lat=req.lat,
        lon=req.lon,
        operations=req.operations,
        hours=req.hours,
        model=req.model,
    )
    payload = _recommendation_payload_from_plan(req.field_id, plan, crop=req.crop)
    rec_id = f"weather-{uuid4().hex[:16]}"
    if req.dry_run:
        _record_weather_observation("recommendation-from-operation-plan", cache_state="dry_run")
        return {
            "saved": False,
            "dry_run": True,
            "rec_id": rec_id,
            "recommendation": payload,
            "operation_plan": plan,
        }
    try:
        import json as _json

        from api.main import _db_unavailable, _emit_domain_event, tenant_connection

        async with tenant_connection(user) as conn:
            await conn.execute(
                """INSERT INTO recommendations
                    (rec_id, tenant_id, farm_id, field_id, crop, delivered, reason_ar,
                     recommendation, cross_reference, provenance, issued_at)
                   VALUES ($1, $2::uuid, $3, $4, $5, true, $6, $7::jsonb, $8::jsonb, $9::jsonb, now())""",
                rec_id,
                str(user.tenant_id),
                req.farm_id,
                req.field_id,
                req.crop,
                payload.get("reason_ar"),
                _json.dumps(payload, ensure_ascii=False, default=str),
                _json.dumps(
                    {"operation_plan_top": plan.get("top_recommendation")},
                    ensure_ascii=False,
                    default=str,
                ),
                _json.dumps(payload.get("provenance") or {}, ensure_ascii=False, default=str),
            )
            await _emit_domain_event(
                conn,
                user,
                "RECOMMENDATION_CREATED",
                "recommendation",
                rec_id,
                {"field_id": req.field_id, "source": "weather_operation_plan"},
            )
            # رابط الخطّ الزمني: نُدِيم سبب الطقس في decision_record ضمن **نفس** المعاملة
            # (RLS) ليظهر «لماذا حُفِظت التوصية» في خطّ الحقل الزمني (…/field/{id}/lineage).
            decision_record = _build_weather_decision_record(
                req.field_id,
                plan.get("top_recommendation") or {},
                model=req.model,
                target="recommendation",
            )
            weather_decision_id = await _persist_weather_decision_record(
                conn, user, decision_record
            )
    except Exception as e:  # noqa: BLE001
        from api.main import _db_unavailable

        raise _db_unavailable("حفظ توصية من خطة الطقس", e) from e
    _record_weather_observation("recommendation-from-operation-plan", cache_state="saved")
    return {
        "saved": True,
        "dry_run": False,
        "rec_id": rec_id,
        "weather_decision_id": weather_decision_id,
        "weather_decision_why_ar": decision_record["why_ar"],
        "recommendation": payload,
        "operation_plan": plan,
    }


@router.get(
    "/api/v1/weather/tile-series/{z}/{x}/{y}",
    dependencies=[Depends(_rate_dependency("tile-series"))],
)
async def weather_tile_series(
    z: int,
    x: int,
    y: int,
    layer: str = Query("precipitation"),
    hours: str = Query("0,1,3,6,12,24,48"),
    model: str = Query("best_match"),
):
    """سلسلة زمنية مرنة للبلاطة نفسها لاستخدام animation/time slider.

    V11: أصبحت تستفيد من cache/stale fallback لكل frame ولا تفشل السلسلة كاملة
    إذا فشل إطار واحد، ما دام هناك إطار واحد صالح على الأقل.
    """
    if z < 0 or z > 18:
        raise HTTPException(status_code=400, detail="z خارج النطاق 0..18")
    max_tile = 2**z
    if x < 0 or y < 0 or x >= max_tile or y >= max_tile:
        raise HTTPException(status_code=400, detail="x/y خارج نطاق البلاطات لهذا التكبير")
    if layer not in _ALLOWED_WEATHER_TILE_LAYERS:
        raise HTTPException(status_code=400, detail=f"طبقة غير مدعومة: {layer}")
    _, model = _validate_time_model("now", model)
    lat, lon = _tile_center(z, x, y)
    frames = []
    upstream_errors: list[str] = []
    for h in _parse_series_hours(hours):
        time_key = _time_key_from_hour(h)
        try:
            sample, cache_state, cache_age_s, upstream_error = await _get_weather_sample_cached(
                lat, lon, time_key, model, f"series:{layer}:z{z}:x{x}:y{y}"
            )
            frames.append(
                {
                    "hour_offset": h,
                    "time": time_key,
                    "weather_time": sample.get("time"),
                    "value": _safe_layer_value(layer, sample),
                    "sample": sample,
                    "cache_state": cache_state,
                    "cache_age_s": cache_age_s,
                    "upstream_error": upstream_error,
                }
            )
        except Exception as e:
            upstream_errors.append(f"{time_key}: {e}")
    if not frames:
        raise HTTPException(
            status_code=502,
            detail=f"Open-Meteo tile-series unavailable: {'; '.join(upstream_errors[:3])}",
        )
    _record_weather_observation(
        "tile-series",
        cache_state="partial" if upstream_errors else "served",
        upstream_error="; ".join(upstream_errors) if upstream_errors else None,
        layer=layer,
    )
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": layer,
        "frames": frames,
        "model": model,
        "source": "open-meteo",
        "rendered_by": "sahool-client-gridlayer",
        "partial": bool(upstream_errors),
        "upstream_errors": upstream_errors[:6],
    }
