"""Thin sahool-platform client for weather-service boundary calls.

P3.4 Platform Weather Facade:
- weather-service owns provider calls, cache, tile math, wind grid, and operation scoring;
- sahool-platform may keep auth/rate-limit/BFF routes but must call this facade
  instead of importing Open-Meteo connectors or re-implementing weather runtime logic.
"""

from __future__ import annotations

import os
from typing import Any

# NOTE: fastapi is imported lazily inside the functions that raise/catch HTTPException.
# This module is reachable from the pure-logic `pytest -m unit` tier (via imagery/raster
# import chains) which runs WITHOUT fastapi installed, so a module-level fastapi import
# would break collection. Keep fastapi out of module import time.

DEFAULT_WEATHER_SERVICE_URL = "http://sahool-weather-service:8000"


def weather_service_url() -> str:
    return os.getenv("WEATHER_SERVICE_URL", DEFAULT_WEATHER_SERVICE_URL).rstrip("/")


def weather_service_headers(
    *, tenant_id: str | None = None, authorization: str | None = None
) -> dict[str, str]:
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")}
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    if authorization:
        headers["Authorization"] = authorization
    return headers


def _detail_from_response(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return getattr(resp, "text", "weather-service returned an error")


async def weather_get_json(
    path: str,
    *,
    tenant_id: str | None = None,
    authorization: str | None = None,
    params: dict[str, Any] | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """GET JSON from weather-service with service token + optional tenant/auth forwarding."""
    import httpx
    from fastapi import HTTPException

    url = f"{weather_service_url()}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(
                url,
                params=params or {},
                headers=weather_service_headers(tenant_id=tenant_id, authorization=authorization),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"weather-service غير متاح: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_detail_from_response(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {"value": data}


async def weather_post_json(
    path: str,
    *,
    json_body: dict[str, Any],
    tenant_id: str | None = None,
    authorization: str | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """POST JSON to weather-service with service token + optional tenant/auth forwarding.

    يرفع ``HTTPException(502)`` عند تعذّر المحرّك (شبكة) — ليتمكّن المُستهلِك من
    الفشل مُغلَقاً (dependency_unavailable) بلا حساب محلّيّ بديل صامت.
    """
    import httpx
    from fastapi import HTTPException

    url = f"{weather_service_url()}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                url,
                json=json_body,
                headers=weather_service_headers(tenant_id=tenant_id, authorization=authorization),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"weather-service غير متاح: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_detail_from_response(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {"value": data}


async def get_et0_product(
    *,
    t_max_c: float | None,
    t_min_c: float | None,
    solar_rad_mj_m2: float | None = None,
    rh_mean_pct: float | None = None,
    wind_2m_ms: float | None = None,
    t_mean_c: float | None = None,
    lat_deg: float | None = None,
    elevation_m: float | None = None,
    day_of_year: int | None = None,
    valid_time: str | None = None,
    weather_snapshot_id: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """منتج ET0 المرجعيّ (FAO-56) من محرّك الطقس — **مصدر ET0 الوحيد للمنصّة**.

    الصيغة تُنفَّذ في المحرّك لا هنا. يعيد العقد الكامل: et0_mm/method/quality_status/
    formula_version/valid_time/weather_snapshot_id. تعذّر المحرّك ⇒ HTTPException(502)
    (لا يُحسب ET0 محلّيّاً بديلاً — fail-closed).
    """
    body = {
        "t_max_c": t_max_c,
        "t_min_c": t_min_c,
        "solar_rad_mj_m2": solar_rad_mj_m2,
        "rh_mean_pct": rh_mean_pct,
        "wind_2m_ms": wind_2m_ms,
        "t_mean_c": t_mean_c,
        "lat_deg": lat_deg,
        "elevation_m": elevation_m,
        "day_of_year": day_of_year,
        "valid_time": valid_time,
        "weather_snapshot_id": weather_snapshot_id,
    }
    return await weather_post_json("/v1/weather/agro/et0", json_body=body, tenant_id=tenant_id)


async def get_et0_series(
    *,
    daily_t_min: list,
    daily_t_max: list,
    lat_deg: float | None,
    elevation_m: float | None = None,
    day_of_year_start: int | None = None,
    daily_dates: list | None = None,
    daily_solar_rad_mj_m2: list | None = None,
    daily_rh_mean_pct: list | None = None,
    daily_wind_2m_ms: list | None = None,
    valid_period: dict | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """سلسلة ET0 اليوميّة المرجعيّة من محرّك الطقس — **مصدر ET0 الوحيد للمحاكاة**.

    النواة تُنفَّذ في المحرّك (لا نواة محلّيّة). ``daily_dates`` (تواريخ ISO لكلّ يوم،
    اختياريّ) لها الأولويّة على ``day_of_year_start`` — يحسب المحرّك DOY لكلّ يوم بلا
    انجراف في السجلّات المتفرّقة. يعيد daily_et0_mm (قد يحوي None ليوم ناقص) + methods +
    accumulated. تعذّر المحرّك ⇒ HTTPException(502) (لا Hargreaves محلّيّ).
    """
    body = {
        "daily_t_min": list(daily_t_min),
        "daily_t_max": list(daily_t_max),
        "lat_deg": lat_deg,
        "elevation_m": elevation_m,
        "day_of_year_start": day_of_year_start,
        "daily_dates": list(daily_dates) if daily_dates is not None else None,
        "daily_solar_rad_mj_m2": daily_solar_rad_mj_m2,
        "daily_rh_mean_pct": daily_rh_mean_pct,
        "daily_wind_2m_ms": daily_wind_2m_ms,
        "valid_period": valid_period,
    }
    return await weather_post_json(
        "/v1/weather/agro/et0/series", json_body=body, tenant_id=tenant_id
    )


async def get_hourly_etc_product(
    *,
    lat: float,
    lon: float,
    horizon_hours: int,
    daily_kc_by_date: dict[str, float],
    daily_runoff_mm_by_date: dict[str, float] | None = None,
    model: str = "best_match",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Provider-native hourly ET0/ETc product from Weather Engine; no local fallback."""
    body = {
        "lat": lat,
        "lon": lon,
        "horizon_hours": horizon_hours,
        "daily_kc_by_date": dict(daily_kc_by_date),
        "daily_runoff_mm_by_date": dict(daily_runoff_mm_by_date or {}),
        "model": model,
    }
    return await weather_post_json(
        "/v1/weather/agro/etc/hourly", json_body=body, tenant_id=tenant_id
    )


async def get_gdd_product(
    *,
    daily_t_min: list,
    daily_t_max: list,
    base_c: float | None,
    upper_cutoff_c: float | None = None,
    method: str = "modified",
    start_date: str | None = None,
    end_date: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """منتج GDD الموحَّد من محرّك الطقس — **مصدر نواة GDD الوحيد للمنصّة**.

    النواة تُنفَّذ في المحرّك؛ السياسة (base_c/upper_cutoff_c/method) من Season وتُمرَّر.
    يعيد العقد الموحَّد (daily_gdd/accumulated_gdd/thresholds_used/calculation_version/
    valid_period). تعذّر المحرّك ⇒ HTTPException(502) (لا حساب GDD محلّيّ بديل).
    """
    body = {
        "daily_t_min": list(daily_t_min),
        "daily_t_max": list(daily_t_max),
        "base_c": base_c,
        "upper_cutoff_c": upper_cutoff_c,
        "method": method,
        "start_date": start_date,
        "end_date": end_date,
    }
    return await weather_post_json("/v1/weather/agro/gdd", json_body=body, tenant_id=tenant_id)


async def get_canonical_field_weather(
    lat: float,
    lon: float,
    *,
    tenant_id: str | None = None,
    model: str = "best_match",
) -> dict[str, Any] | None:
    """Resolve the owner-produced canonical weather state for a field location.

    The platform does not rebuild weather facts.  ``weather-service`` fetches the
    observation and returns a view carrying the canonical state identity.  This
    adapter only reconstructs the *state envelope* from fields already emitted by
    that owner-facing response so ``canonical_field_state`` can bind the evidence.

    Failures and incomplete provenance are absence (``None``), never a fabricated
    healthy product.
    """
    try:
        current = await weather_get_json(
            "/v1/weather/current",
            tenant_id=tenant_id,
            params={"lat": lat, "lon": lon, "model": model},
            timeout_s=8.0,
        )
    except Exception:  # noqa: BLE001 -- field-state composition is fail-closed on absence
        return None
    if current.get("derived_from") != "canonical_weather_state":
        return None
    state_id = current.get("canonical_state_id")
    state_version = current.get("canonical_state_version")
    source_snapshot_id = current.get("source_snapshot_id") or current.get("weather_snapshot_id")
    if not state_id or not state_version or not source_snapshot_id:
        return None
    quality = current.get("quality_status")
    limitations = list(current.get("limitations") or [])
    return {
        "product_id": "canonical_weather_state",
        "state_id": state_id,
        "state_version": state_version,
        "schema_version": str(state_version),
        "owner": "weather-service",
        "source_snapshot_id": source_snapshot_id,
        "generated_at": current.get("observed_at")
        or current.get("time")
        or current.get("timestamp"),
        "quality": quality,
        # canonical_field_state uses the cross-owner ``quality_status`` declaration.
        "quality_status": quality,
        "availability": {"current": quality not in {None, "insufficient", "invalid"}},
        "provenance": {
            "current": {
                "quality_status": quality,
                "weather_snapshot_id": source_snapshot_id,
            }
        },
        "evidence": {
            "canonical_state_id": state_id,
            "source_snapshot_id": source_snapshot_id,
            "observed_fields": list(current.get("observed_fields") or []),
        },
        "limitations": limitations,
        "products": {"current": current},
    }


async def get_current_weather(
    lat: float, lon: float, *, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/current", params={"lat": lat, "lon": lon, "model": model}
    )


async def get_weather_forecast(
    lat: float, lon: float, *, days: int = 7, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/forecast", params={"lat": lat, "lon": lon, "days": days, "model": model}
    )


async def get_weather_historical(
    lat: float, lon: float, *, start_date: str, end_date: str
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/historical",
        params={"lat": lat, "lon": lon, "start_date": start_date, "end_date": end_date},
    )


def _neutral_tile(z: int, x: int, y: int, *, layer: str) -> dict[str, Any]:
    """Neutral tile payload returned when weather-service is unreachable (502).

    Preserves the "don't flood the map with 502 per tile" guarantee across the
    platform->weather-service network hop: the map draws an empty/neutral tile
    instead of erroring on every request.
    """
    return {
        "tile": {"z": z, "x": x, "y": y},
        "layer": layer,
        "value": None,
        "sample": None,
        "available": False,
        "cache_state": "service_unavailable",
        "upstream_error": "weather-service unreachable",
        "rendered_by": "sahool-client-gridlayer",
    }


async def get_weather_tile_data(
    z: int,
    x: int,
    y: int,
    *,
    layer: str,
    time: str = "now",
    model: str = "best_match",
    interpolation: str = "center",
) -> dict[str, Any]:
    from fastapi import HTTPException

    try:
        return await weather_get_json(
            f"/v1/weather/tile-data/{z}/{x}/{y}",
            params={"layer": layer, "time": time, "model": model, "interpolation": interpolation},
        )
    except HTTPException as exc:
        if exc.status_code == 502:
            return _neutral_tile(z, x, y, layer=layer)
        raise


async def get_operation_tile_data(
    z: int,
    x: int,
    y: int,
    *,
    operation: str,
    time: str = "now",
    model: str = "best_match",
    interpolation: str = "center",
) -> dict[str, Any]:
    from fastapi import HTTPException

    try:
        return await weather_get_json(
            f"/v1/weather/operation-tile-data/{z}/{x}/{y}",
            params={
                "operation": operation,
                "time": time,
                "model": model,
                "interpolation": interpolation,
            },
        )
    except HTTPException as exc:
        if exc.status_code == 502:
            return _neutral_tile(z, x, y, layer=operation)
        raise


async def get_operation_window(
    lat: float, lon: float, *, operation: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/operation-window",
        params={"lat": lat, "lon": lon, "operation": operation, "hours": hours, "model": model},
    )


async def get_operation_plan(
    lat: float, lon: float, *, operations: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/operation-plan",
        params={"lat": lat, "lon": lon, "operations": operations, "hours": hours, "model": model},
    )


async def get_thermal_stress(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """منتج الإجهاد الحراريّ المركّب من weather-service (منطق الطقس يعيش هناك)."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    return await weather_get_json("/v1/weather/thermal-stress", params=params)


async def get_lodging_risk(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    plant_height_cm: float | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """خطر الرقود من weather-service (منطق الطقس يعيش هناك)."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    if plant_height_cm is not None:
        params["plant_height_cm"] = plant_height_cm
    return await weather_get_json("/v1/weather/lodging-risk", params=params)


async def get_pollination_risk(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """خطر الطقس على التلقيح من weather-service."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    return await weather_get_json("/v1/weather/pollination-risk", params=params)


async def get_chill_accumulation(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """تراكم البرودة الموسميّ من weather-service (نافذة تاريخيّة)."""
    params: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "start_date": start_date,
        "end_date": end_date,
    }
    if crop:
        params["crop"] = crop
    return await weather_get_json("/v1/weather/chill-accumulation", params=params)


async def get_weather_tile_series(
    z: int, x: int, y: int, *, layer: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        f"/v1/weather/tile-series/{z}/{x}/{y}",
        params={"layer": layer, "hours": hours, "model": model},
    )


async def get_wind_grid(
    z: int, x: int, y: int, *, time: str = "now", model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        f"/v1/weather/wind-grid/{z}/{x}/{y}",
        params={"time": time, "model": model},
    )


async def get_tile_cache_stats() -> dict[str, Any]:
    """إحصاءات مخبّأ البلاطات من weather-service.

    **المسار هو `cache-stats` لا `tile-cache/stats`:** الخدمة تُعلن
    `app.get("/v1/weather/cache-stats")` وليس في سطحها كلِّه مسارٌ باسم
    `tile-cache/stats` — فالطلب القديم كان يُنهي 404 حتماً على كلّ نداء.
    والاسمان لدالّةٍ خلفيّةٍ واحدة (`rt.tile_cache_stats`)، فالانحراف كان في
    السلسلة النصّيّة وحدها؛ ولذلك صُحِّح العميلُ ولم يُمَسّ مسارُ الخدمة —
    تغييرُه كان سيكسر أيَّ مستهلكٍ آخر يناديه بالاسم القانونيّ.

    ومسارُ المنصّة العامّ `/api/v1/weather/tile-cache/stats` يبقى كما هو:
    هذه القفزةُ داخليّة بين المنصّة والخدمة، لا عقدٌ مع الواجهة.
    """
    return await weather_get_json("/v1/weather/cache-stats")
