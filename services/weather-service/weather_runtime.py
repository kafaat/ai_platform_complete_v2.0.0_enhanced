from __future__ import annotations

import sys
from typing import Literal

from cache import get as cache_get
from cache import set as cache_set
from cache import stats as cache_stats
from canonical_daily_weather_series import build_canonical_daily_series, gdd_view
from canonical_weather_state import (
    build_canonical_weather_state,
    current_view,
    et0_view,
    forecast_view,
    historical_view,
    vpd_view,
    weather_state_report,
)
from chill_accumulation import compute_chill_accumulation
from et0 import et0_series_product
from fastapi import Body, HTTPException, Query
from hourly_etc import build_hourly_etc_product
from lodging_risk import compute_lodging_risk
from open_meteo import (
    circuit_breaker_state,
    fetch_archive_hourly_temps,
    fetch_current,  # noqa: F401 — إعادة تصدير للواجهة/الحُرّاس (نمط main.X)
    fetch_daily_wind_temp_rain,
    fetch_forecast,  # noqa: F401 — إعادة تصدير للواجهة/الحُرّاس (نمط main.X)
    fetch_historical,  # noqa: F401 — إعادة تصدير للواجهة/الحُرّاس (نمط main.X)
    fetch_hourly_fao_et0_precipitation,
    fetch_thermal_series,
    fetch_tile_sample,  # noqa: F401 — إعادة تصدير للواجهة/الحُرّاس (نمط main.X)
    readiness_probe,  # noqa: F401 — إعادة تصدير للواجهة/الحُرّاس (نمط main.X)
)
from operations import advice_ar, best_operation_frame, operation_suitability
from pollination_risk import compute_pollination_risk
from pydantic import BaseModel, Field
from raw_weather_processing import RawWeatherProcessRequest, build_raw_weather_response
from thermal_stress import compute_compound_thermal_stress
from tiles import (
    ALLOWED_LAYERS,
    derived_layer_value,
    parse_series_hours,
    tile_center,
    tile_interpolation_points,
    time_key_from_hour,
    unit_for_layer,
    validate_time_model,
)


def _facade_attr(name: str):
    """Resolve monkeypatch-compatible runtime hooks from the public main module.

    Legacy tests and operators patch ``main.fetch_*`` directly. After P2 extraction the
    real implementation lives here, so route handlers resolve patchable hooks through
    ``sys.modules['main']`` when available, falling back to local imports.
    """
    facade = sys.modules.get("main")
    if facade is not None and hasattr(facade, name):
        return getattr(facade, name)
    return globals()[name]


def healthz():
    return {"status": "ok", "service": "weather-service", "mode": "runtime"}


def health():
    # Backward-compatible health alias for older local scripts; real readiness stays /readyz.
    return healthz()


# مِسبارُ الجهوزيّة يُنادى بإيقاع المُنسِّق (كلَّ ثوانٍ)، وكان كلُّ نداءٍ يُخرِج
# طلباً حقيقيّاً إلى Open-Meteo عبر `readiness_probe` ⇒ `fetch_current`. فحصُ
# «أأنا حيّ؟» كان يستهلك حصّةَ المزوّد ويُقيَّد بزمنه — والخدمةُ لها مخبّأٌ يعمل
# بلا مزوّدٍ أصلاً.
#
# **والعلاجُ ليس تخبئةَ نتيجة المِسبار.** جُرِّب ذلك أوّلاً فأحمرّ
# `test_readyz_reports_degraded_when_open_meteo_probe_fails`، والاختبارُ على حقّ:
# نجاحٌ مخبّأٌ يُخفي عطلاً منبعيّاً حتّى ينقضي أجلُه، وذلك نقضُ الغرض الذي وُجِدت
# النقطةُ له. تخفيفُ الحِمل لا يُشترى بإخفاء الأعطال.
#
# فالجهوزيّةُ تُبنى على ما **قاسته حركةُ المرور فعلاً**، ولا تُنادي المزوّدَ إلّا
# حين لا يكون الجوابُ معروفاً:
#
#   القاطعُ مفتوح            ⇒ `degraded` بلا نداء — الجوابُ معروفٌ سلفاً.
#   إخفاقاتٌ مُسجَّلة > 0     ⇒ يُقاس الآن — شيءٌ يتداعى، فلا يُؤجَّل القياس.
#   نجاحٌ منبعيٌّ حديث        ⇒ `ready` بلا نداء — قِيس توّاً بحركةٍ حقيقيّة.
#   وإلّا (خدمةٌ باردة)       ⇒ يُقاس.
#
# فتحت الحِمل الطبيعيّ صفرُ نداءٍ إضافيّ، وعند أوّل إخفاقٍ يُقاس فوراً — ولا
# يُخفى شيء. والمصدرُ مُعلَنٌ في الردّ (`readiness_source`) فلا يُقرأ المُستنتَجُ
# قياساً جديداً.
_READYZ_OBSERVED_SUCCESS_TTL_S = 30.0


async def _upstream_readiness() -> dict:
    """جهوزيّةٌ منبعيّةٌ بلا نداءٍ زائد — ولا إخفاءَ عطلٍ مقابل ذلك."""
    breaker = circuit_breaker_state()
    if breaker.get("state") == "open":
        return {
            "ok": False,
            "provider": "open-meteo",
            "error": breaker.get("last_error") or "circuit breaker is open",
            "circuit_breaker": breaker,
            "readiness_source": "circuit-breaker-open",
        }
    age = breaker.get("last_success_age_s")
    if (
        not breaker.get("failure_count")
        and age is not None
        and age < _READYZ_OBSERVED_SUCCESS_TTL_S
    ):
        return {
            "ok": True,
            "provider": "open-meteo",
            "circuit_breaker": breaker,
            "readiness_source": "observed-traffic",
            "last_success_age_s": age,
        }
    probed = await _facade_attr("readiness_probe")()
    return {**probed, "readiness_source": "probe"}


async def readyz():
    upstream = await _upstream_readiness()
    cache = cache_stats()
    status = "ready" if upstream.get("ok") else "degraded"
    return {
        "status": status,
        "service": "weather-service",
        "mode": "runtime",
        "implemented_runtime": True,
        "upstream_open_meteo": upstream,
        "cache": cache,
        "circuit_breaker": circuit_breaker_state(),
    }


def root():
    return {
        "service": "weather-service",
        "mode": "runtime",
        "implemented_runtime": True,
        "note_ar": "خدمة الطقس الفعلية: Open-Meteo core + operation windows + tiles/wind grid.",
    }


def contract():
    return {
        "service": "weather-service",
        "contract_version": "2026-07-09.runtime",
        "implemented_runtime": True,
        "mode": "runtime",
        "ownership": "target-weather-system-of-record",
        "capabilities": {
            "p3_1_core": ["current-weather", "forecast", "historical-weather", "cache"],
            "p3_2_operation_windows": ["operation-window", "operation-plan", "operation-tile-data"],
            "p3_3_tiles_wind_grid": ["tile-data", "tile-series", "wind-grid", "tile-interpolation"],
            "raw_weather_processing": ["raw-process", "numeric-summary", "provenance"],
            "wx_i1_hourly_etc": [
                "provider-native-hourly-et0",
                "hourly-etc",
                "effective-rain",
                "digest",
            ],
        },
        "source": "open-meteo+sahool-rules",
    }


class HourlyEtcRequest(BaseModel):
    lat: float
    lon: float
    horizon_hours: int = 48
    daily_kc_by_date: dict[str, float]
    daily_runoff_mm_by_date: dict[str, float] = Field(default_factory=dict)
    model: str = "best_match"


async def agro_hourly_etc(request: HourlyEtcRequest = Body(...)):
    """Canonical provider-native hourly ET0/Kc/ETc product for irrigation MPC."""
    if not (-90 <= request.lat <= 90 and -180 <= request.lon <= 180):
        raise HTTPException(status_code=422, detail="invalid latitude/longitude")
    horizon = max(1, min(int(request.horizon_hours), 384))
    key_material = {
        "lat": round(request.lat, 5),
        "lon": round(request.lon, 5),
        "horizon_hours": horizon,
        "daily_kc_by_date": request.daily_kc_by_date,
        "daily_runoff_mm_by_date": request.daily_runoff_mm_by_date,
        "model": request.model,
    }
    import hashlib
    import json

    cache_key = (
        "hourly-etc:"
        + hashlib.sha256(
            json.dumps(key_material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    cached, state, age = cache_get(cache_key)
    if cached is not None and state == "fresh":
        result = dict(cached)
        result["cache_state"] = "fresh"
        result["cache_age_s"] = age
        return result
    try:
        payload = await fetch_hourly_fao_et0_precipitation(
            request.lat, request.lon, horizon_hours=horizon, model=request.model
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Open-Meteo hourly FAO ET0 unavailable: {exc}"
        ) from exc
    result = build_hourly_etc_product(
        provider_payload=payload,
        lat=request.lat,
        lon=request.lon,
        horizon_hours=horizon,
        daily_kc_by_date=request.daily_kc_by_date,
        daily_runoff_mm_by_date=request.daily_runoff_mm_by_date,
        model=request.model,
    )
    if result.get("status") != "verified":
        raise HTTPException(status_code=424, detail=result)
    result["cache_state"] = "refreshed"
    result["cache_age_s"] = 0
    cache_set(cache_key, result)
    return result


async def raw_weather_process(request: RawWeatherProcessRequest = Body(...)):
    """Return bounded QA/provenance for raw weather payloads.

    This endpoint deliberately does not compute operation windows, agronomic
    decisions, or indicators. It is a raw-data inspection boundary for weather
    ingestion and CI/runtime diagnostics.
    """
    try:
        if request.source_kind == "current":
            payload = await _facade_attr("fetch_current")(
                request.lat, request.lon, model=request.model
            )
        elif request.source_kind == "forecast":
            payload = await _facade_attr("fetch_forecast")(
                request.lat, request.lon, days=request.days, model=request.model
            )
        elif request.source_kind == "historical":
            payload = await _facade_attr("fetch_historical")(
                request.lat,
                request.lon,
                start_date=request.start_date or "",
                end_date=request.end_date or "",
            )
        else:
            time, model = validate_time_model(request.time, request.model)
            payload = await _facade_attr("fetch_tile_sample")(
                request.lat, request.lon, time_key=time, model=model
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo raw weather: {exc}") from exc
    return build_raw_weather_response(request, payload)


async def current_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    model: str = "best_match",
):
    """WX-10.4 — «الآن» تُقرأ من CanonicalWeatherState لا من حمولة المزوّد مباشرةً.

    الجلب (I/O) يبقى عند الحافّة، ثمّ تُمرَّر المشاهدة المُطبَّعة إلى المُجمِّع النقيّ ويُقرأ
    الناتج عبر `current_view` — فيحمل الردّ نَسَب الحالة وما رُصِد فعلاً وما غاب. توافقيّ
    للخلف: مجموعة فائقة من الردّ السابق (كلّ حقول المشاهدة تبقى في مستواها الأعلى).
    """
    try:
        observation = await _facade_attr("fetch_current")(lat, lon, model=model)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo current: {exc}") from exc
    state = build_canonical_weather_state(
        lat_deg=lat,
        valid_time=(observation or {}).get("time") or (observation or {}).get("timestamp"),
        current_observation=observation,
    )
    return current_view(state)


async def forecast_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    days: int = 7,
    model: str = "best_match",
):
    """WX-10.5 — التوقّع يُقرأ من CanonicalWeatherState لا من حمولة المزوّد مباشرةً.

    الجلب عند الحافّة ثمّ المُجمِّع النقيّ ثمّ `forecast_view`. توافقيّ للخلف: مجموعة فائقة
    (`days`/`range`/`model`/`timezone` كما هي) مضافاً إليها الجودة والنَّسَب.
    """
    try:
        series = await _facade_attr("fetch_forecast")(lat, lon, days=days, model=model)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo forecast: {exc}") from exc
    state = build_canonical_weather_state(
        lat_deg=lat,
        valid_time=((series or {}).get("range") or {}).get("start"),
        forecast_series=series,
    )
    return forecast_view(state)


async def historical_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    """WX-10.5 — الأرشيف يُقرأ من CanonicalWeatherState لا من حمولة المزوّد مباشرةً.

    نفس مسار التوقّع بالضبط (المُنتِج واحد)، عبر `historical_view`. توافقيّ للخلف.
    """
    try:
        series = await _facade_attr("fetch_historical")(
            lat, lon, start_date=start_date, end_date=end_date
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo historical: {exc}") from exc
    state = build_canonical_weather_state(
        lat_deg=lat,
        valid_time=((series or {}).get("range") or {}).get("start"),
        historical_series=series,
    )
    # المطلوبُ يُمرَّر صراحةً: المُعالِج وحده يعرفه، و`range` في السلسلة مُشتقٌّ من أوقات
    # المزوّد — فسلسلةٌ مبتورة تصف مداها الخاصّ وتبدو كاملة. بلا هذا التمرير تُقارَن
    # السلسلةُ بنفسها ولا تُقارَن بما طُلِب.
    return historical_view(state, requested_start=start_date, requested_end=end_date)


async def _cached_sample(lat: float, lon: float, time: str, model: str, key_prefix: str = "sample"):
    time, model = validate_time_model(time, model)
    key = f"{key_prefix}:{round(lat, 4)}:{round(lon, 4)}:{time}:{model}"
    sample, state, age = cache_get(key)
    upstream_error = None
    if state != "fresh":
        try:
            sample = await _facade_attr("fetch_tile_sample")(lat, lon, time_key=time, model=model)
            cache_set(key, sample)
            return sample, "refreshed", 0, None
        except Exception as exc:
            upstream_error = str(exc)
            if sample is not None and state == "stale":
                return sample, "stale_fallback", age, upstream_error
            raise
    return sample, state, age, upstream_error


async def operation_window(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    operation: Literal[
        "spraying", "harvesting", "sowing", "fertilizing", "irrigation"
    ] = "spraying",
    hours: str = "0,1,3,6,12,24,48",
    model: str = "best_match",
):
    frames = []
    upstream_errors: list[str] = []
    _, model = validate_time_model("now", model)
    for h in parse_series_hours(hours):
        t = time_key_from_hour(h)
        try:
            sample, cache_state, cache_age_s, upstream_error = await _cached_sample(
                lat, lon, t, model, f"window:{operation}"
            )
            decision = operation_suitability(sample, operation)
            frames.append(
                {
                    "hour_offset": h,
                    "time": t,
                    "weather_time": sample.get("time"),
                    "operation": decision,
                    "sample": sample,
                    "cache_state": cache_state,
                    "cache_age_s": cache_age_s,
                    "upstream_error": upstream_error,
                }
            )
        except Exception as exc:
            upstream_errors.append(f"{t}: {exc}")
    if not frames:
        raise HTTPException(status_code=502, detail="Open-Meteo operation-window unavailable")
    best = best_operation_frame(frames)
    return {
        "location": {"lat": lat, "lon": lon},
        "operation": operation,
        "model": model,
        "frames": frames,
        "best": best,
        "advice_ar": advice_ar(best.get("operation") if best else None),
        "source": "open-meteo+sahool-rules",
        "partial": bool(upstream_errors),
        "upstream_errors": upstream_errors[:6],
    }


async def operation_plan(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    operations: str = "spraying,irrigation,harvesting,sowing",
    hours: str = "0,1,3,6,12,24,48",
    model: str = "best_match",
):
    items = []
    errors: list[str] = []
    for op in [x.strip() for x in operations.split(",") if x.strip()]:
        try:
            window = await operation_window(
                lat=lat, lon=lon, operation=op, hours=hours, model=model
            )  # type: ignore[arg-type]
            best = window.get("best")
            items.append(
                {
                    "operation": op,
                    "best": best,
                    "frames": window.get("frames", []),
                    "recommended": bool(
                        best and (best.get("operation") or {}).get("score", 0) >= 0.55
                    ),
                    "priority": (best.get("operation") or {}).get("score", 0) if best else 0,
                    "advice_ar": window.get("advice_ar"),
                }
            )
        except Exception as exc:
            errors.append(f"{op}: {exc}")
    items.sort(key=lambda item: item.get("priority", 0), reverse=True)
    if not items:
        raise HTTPException(status_code=502, detail="Open-Meteo operation-plan unavailable")
    return {
        "location": {"lat": lat, "lon": lon},
        "model": model,
        "operations": items,
        "recommended_now": [i for i in items if i.get("recommended")],
        "top_recommendation": items[0] if items else None,
        "source": "open-meteo+sahool-operation-plan",
        "partial": bool(errors),
        "upstream_errors": errors[:10],
    }


async def thermal_stress(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    crop: str | None = Query(default=None, max_length=64),
    stage: str | None = Query(default=None, max_length=64),
    days: int = Query(default=3, ge=1, le=16),
    model: str = "best_match",
):
    """منتج الإجهاد الحراريّ المركّب (حرّ نهار × برد ليل) مشروطاً بالمحصول والمرحلة.

    منطق الطقس الحتميّ يعيش هنا (عقد الخدمة الحقيقيّ)؛ المستهلِك يوفّر المحصول/المرحلة.
    fail-closed: غياب سياق المحصول/المرحلة ⇒ insufficient_context (لا مخاطرة مُختلَقة).
    """
    cache_key = f"thermal:{lat:.4f}:{lon:.4f}:{days}:{model}"
    series, state, _age = cache_get(cache_key)
    if series is None or state != "fresh":
        try:
            series = await fetch_thermal_series(lat, lon, days=days, model=model)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=503, detail=f"تعذّر جلب سلسلة الطقس الحراريّة: {exc}"
            ) from exc
        cache_set(cache_key, series)
    result = compute_compound_thermal_stress(
        crop=crop,
        stage=stage,
        daily_max_c=series.get("daily_max_c", []),
        daily_min_c=series.get("daily_min_c", []),
        hourly_temp_c=series.get("hourly_temp_c") or None,
        hourly_is_daytime=series.get("hourly_is_daytime") or None,
        hourly_rh_pct=series.get("hourly_rh_pct") or None,
    )
    return {"location": {"lat": lat, "lon": lon}, "model": model, **result}


def _finite_max(values, default=None):
    out = []
    for v in values or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f:
            out.append(f)
    return max(out) if out else default


def _finite_min(values, default=None):
    out = []
    for v in values or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f:
            out.append(f)
    return min(out) if out else default


def _finite_sum(values):
    total = 0.0
    for v in values or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f:
            total += f
    return total


async def lodging_risk(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    crop: str | None = Query(default=None, max_length=64),
    stage: str | None = Query(default=None, max_length=64),
    plant_height_cm: float | None = Query(default=None, ge=0, le=1000),
    days: int = Query(default=3, ge=1, le=16),
    model: str = "best_match",
):
    """خطر الرقود (انبطاح النبات) من رياح الأفق مشروطاً بقابليّة المحصول×المرحلة."""
    key = f"lwr:{lat:.4f}:{lon:.4f}:{days}:{model}"
    series, state, _age = cache_get(key)
    if series is None or state != "fresh":
        try:
            series = await fetch_daily_wind_temp_rain(lat, lon, days=days, model=model)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=503, detail=f"تعذّر جلب سلسلة الرياح/المطر: {exc}"
            ) from exc
        cache_set(key, series)
    result = compute_lodging_risk(
        crop=crop,
        stage=stage,
        max_wind_gust_mps=_finite_max(series.get("wind_gust_max_mps")),
        max_wind_speed_mps=_finite_max(series.get("wind_speed_max_mps")),
        forecast_rain_mm=_finite_sum(series.get("precip_sum_mm")),
        plant_height_cm=plant_height_cm,
    )
    return {"location": {"lat": lat, "lon": lon}, "model": model, **result}


async def pollination_risk(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    crop: str | None = Query(default=None, max_length=64),
    stage: str | None = Query(default=None, max_length=64),
    days: int = Query(default=3, ge=1, le=16),
    model: str = "best_match",
):
    """خطر الطقس على التلقيح أثناء الإزهار (fail-closed خارج مرحلة الإزهار)."""
    key = f"pwr:{lat:.4f}:{lon:.4f}:{days}:{model}"
    series, state, _age = cache_get(key)
    if series is None or state != "fresh":
        try:
            series = await fetch_daily_wind_temp_rain(lat, lon, days=days, model=model)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"تعذّر جلب سلسلة الطقس: {exc}") from exc
        cache_set(key, series)
    result = compute_pollination_risk(
        crop=crop,
        stage=stage,
        day_max_c=_finite_max(series.get("daily_max_c")),
        night_min_c=_finite_min(series.get("daily_min_c")),
        max_wind_mps=_finite_max(series.get("wind_speed_max_mps")),
        rain_mm=_finite_sum(series.get("precip_sum_mm")),
    )
    return {"location": {"lat": lat, "lon": lon}, "model": model, **result}


async def chill_accumulation(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    crop: str | None = Query(default=None, max_length=64),
    start_date: str = Query(..., min_length=10, max_length=10),
    end_date: str = Query(..., min_length=10, max_length=10),
):
    """تراكم البرودة الموسميّ (Chilling Hours + Utah) للأشجار المتساقطة من سلسلة تاريخيّة."""
    key = f"chill:{lat:.4f}:{lon:.4f}:{start_date}:{end_date}"
    series, state, _age = cache_get(key)
    if series is None or state != "fresh":
        try:
            series = await fetch_archive_hourly_temps(
                lat, lon, start_date=start_date, end_date=end_date
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=503, detail=f"تعذّر جلب السلسلة التاريخيّة الساعيّة: {exc}"
            ) from exc
        cache_set(key, series)
    result = compute_chill_accumulation(crop=crop, hourly_temp_c=series.get("hourly_temp_c"))
    return {
        "location": {"lat": lat, "lon": lon},
        "window": {"start_date": start_date, "end_date": end_date},
        **result,
    }


class Et0ProductRequest(BaseModel):
    """مدخلات ET0 المرجعيّ — المحرّك يملك تنفيذ الصيغة (FAO-56).

    اللقطة (الطقس) يُوفّرها المُستهلِك في هذه المرحلة (C.1b)؛ جلبها داخل المحرّك من
    lat/lon/valid_time لاحق (WS-D.2c). مفقود ≠ افتراض — النقص يُخفِّض الطريقة/الجودة.
    """

    t_max_c: float | None = None
    t_min_c: float | None = None
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    t_mean_c: float | None = None
    lat_deg: float | None = None
    elevation_m: float | None = None
    day_of_year: int | None = None
    valid_time: str | None = None  # وقت صلاحيّة اللقطة (ISO) كما يُصرّح به المُستهلِك
    weather_snapshot_id: str | None = None  # هويّة اللقطة إن كانت للمُستهلِك مسبقاً


async def agro_et0(req: Et0ProductRequest = Body(...)):
    """منتج ET0 المرجعيّ (FAO-56) — **View مُشتقّ من CanonicalWeatherState** (WX-10.2).

    الانعكاس المعماريّ: ET0 لم يعد يُحسب من نداء نواة مباشر بل يُشتقّ من خانة ``et0`` في
    الحالة الكنسيّة (المصدر الواحد). حقول العقد محفوظة بدقّة (``et0_mm`` · ``method`` ·
    ``quality_status`` · ``formula_version`` · ``valid_time`` · ``weather_snapshot_id``) —
    توافقيّ للخلف — **مضافاً إليها نَسَب الحالة** (``canonical_state_id``/``source_snapshot_id``/
    ``derived_from``). نقيّ حتميّ لا شبكة ⇒ لا 5xx.
    """
    state = build_canonical_weather_state(
        t_max_c=req.t_max_c,
        t_min_c=req.t_min_c,
        solar_rad_mj_m2=req.solar_rad_mj_m2,
        rh_mean_pct=req.rh_mean_pct,
        wind_2m_ms=req.wind_2m_ms,
        t_mean_c=req.t_mean_c,
        lat_deg=req.lat_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
        valid_time=req.valid_time,
        weather_snapshot_id_override=req.weather_snapshot_id,
    )
    return et0_view(state)


class VpdProductRequest(BaseModel):
    """مدخلات VPD — الحرارة (Tmax إلزاميّ) + مصدر رطوبة (RH أو نقطة النَّدى).

    اللقطة يُوفّرها المُستهلِك (valid_time/weather_snapshot_id override اختياريّان).
    نقص الحرارة أو مصدر الرطوبة ⇒ insufficient (لا افتراض).
    """

    t_max_c: float | None = None
    t_min_c: float | None = None
    rh_mean_pct: float | None = None
    dew_point_c: float | None = None
    valid_time: str | None = None
    weather_snapshot_id: str | None = None


async def agro_vpd(req: VpdProductRequest = Body(...)):
    """منتج VPD (نقص ضغط البخار) — **View مُشتقّ من CanonicalWeatherState** (WX-10.3).

    الانعكاس المعماريّ: VPD يُشتقّ من خانة ``vpd`` في الحالة الكنسيّة (المصدر الواحد) لا من
    حساب مباشر. كامل عقد VPD محفوظ حرفيّاً (``vpd_kpa``·``raw_vpd_kpa``·``es_kpa``·``ea_kpa``·
    ``method``·``input_completeness``·``input_consistency``·``quality_status``·``quality_flags``·
    ``limitations``·``cross_check``·``units``·``formula_version``) — **مضافاً** نَسَب الحالة
    (``derived_from``·``canonical_state_id``·``canonical_state_version``·``source_snapshot_id``·
    ``weather_snapshot_id``). نقيّ حتميّ لا شبكة ⇒ لا 5xx.
    """
    state = build_canonical_weather_state(
        t_max_c=req.t_max_c,
        t_min_c=req.t_min_c,
        rh_mean_pct=req.rh_mean_pct,
        dew_point_c=req.dew_point_c,
        valid_time=req.valid_time,
        weather_snapshot_id_override=req.weather_snapshot_id,
    )
    return vpd_view(state)


class Et0SeriesRequest(BaseModel):
    """سلسلة ET0 يوميّة — للمحاكاة/الموسم (تفويض ET0 عن النواة المحلّيّة، WS-C.1b)."""

    daily_t_min: list[float | None] = []
    daily_t_max: list[float | None] = []
    lat_deg: float | None = None
    elevation_m: float | None = None
    daily_solar_rad_mj_m2: list[float | None] | None = None
    daily_rh_mean_pct: list[float | None] | None = None
    daily_wind_2m_ms: list[float | None] | None = None
    day_of_year_start: int | None = None
    # تواريخ ISO لكلّ يوم (اختياريّ، بالأولويّة على day_of_year_start) — يمنع الانجراف
    # الفلكيّ في السجلّات المتفرّقة/متعدّدة السنوات (المحرّك يملك date→DOY).
    daily_dates: list[str | None] | None = None
    valid_period: dict | None = None


async def agro_et0_series(req: Et0SeriesRequest = Body(...)):
    """منتج سلسلة ET0 المرجعيّة (FAO-56) — نواة المحرّك لسلاسل الموسم/المحاكاة.

    يفوّض حساب ET0 لسلسلة أيّام دفعةً واحدة (بدل N نداءات) — أساس ترحيل
    season_simulation عن نواة ET0 المحلّيّة. نقيّ بلا شبكة ⇒ لا 5xx.
    """
    return et0_series_product(
        daily_t_min=req.daily_t_min,
        daily_t_max=req.daily_t_max,
        lat_deg=req.lat_deg,
        elevation_m=req.elevation_m,
        daily_solar_rad_mj_m2=req.daily_solar_rad_mj_m2,
        daily_rh_mean_pct=req.daily_rh_mean_pct,
        daily_wind_2m_ms=req.daily_wind_2m_ms,
        day_of_year_start=req.day_of_year_start,
        daily_dates=req.daily_dates,
        valid_period=req.valid_period,
    )


class GddProductRequest(BaseModel):
    """مدخلات GDD — سلسلة حرارة يوميّة + **سياسة الموسم** (الأساس/السقف/الطريقة).

    النواة في المحرّك؛ السياسة (base_c/upper_cutoff_c/method/الفترة) يحدّدها Season
    Service ويمرّرها. مفقود base_c ⇒ insufficient (لا افتراض).

    WX-10.4: حقول نَسَب/سلسلة اختياريّة (توافقيّة للخلف): ``daily_dates`` (تاريخ لكلّ يوم؛
    يُفعّل الترتيب القانونيّ + إزالة التكرار + التغطية) · ``daily_snapshot_ids`` (هويّة لقطة
    لكلّ يوم) · ``timezone`` · ``reset_policy``. غيابها ⇒ سلوك قديم محفوظ (تواريخ تسلسليّة
    من start_date، بلا فجوات).
    """

    daily_t_min: list[float | None] = []
    daily_t_max: list[float | None] = []
    base_c: float | None = None
    upper_cutoff_c: float | None = None
    method: str = "modified"  # modified | simple
    start_date: str | None = None
    end_date: str | None = None
    daily_dates: list[str | None] | None = None
    daily_snapshot_ids: list[str | None] | None = None
    timezone: str | None = None
    reset_policy: str | None = None


def _gdd_daily_records(req: GddProductRequest) -> tuple[list[dict], dict]:
    """يبني سجلّات يوميّة مؤرَّخة من الطلب + تشخيصات صريحة.

    توافقيّة للخلف: daily_dates إن وُجدت، وإلّا تواريخ تسلسليّة من start_date (سلوك قديم)،
    وإلّا تواريخ ترتيبيّة من حقبة ثابتة للترتيب فقط (لا تلمس valid_period — يُمرَّر start/end
    الأصليّان للنواة كما هما). التشخيصات تُفصح عن أطوال المدخل والأزواج غير المربوطة كي لا
    يختفي أيّ سجلّ بصمت.
    """
    from datetime import date as _d
    from datetime import timedelta as _td

    n = min(len(req.daily_t_min), len(req.daily_t_max))
    base_dt = None
    if not req.daily_dates and req.start_date:
        try:
            base_dt = _d.fromisoformat(req.start_date)
        except ValueError:
            base_dt = None
    if not req.daily_dates and base_dt is None:
        base_dt = _d(1970, 1, 1)  # ترتيب فقط؛ valid_period يبقى من start/end الأصليّين

    records: list[dict] = []
    for i in range(n):
        if req.daily_dates and i < len(req.daily_dates) and req.daily_dates[i]:
            date_s = req.daily_dates[i]
        elif base_dt is not None:
            date_s = (base_dt + _td(days=i)).isoformat()
        else:
            continue
        snap = None
        if req.daily_snapshot_ids and i < len(req.daily_snapshot_ids):
            snap = req.daily_snapshot_ids[i]
        records.append(
            {
                "date": date_s,
                "t_min_c": req.daily_t_min[i],
                "t_max_c": req.daily_t_max[i],
                "weather_snapshot_id": snap,
            }
        )
    diagnostics = {
        "input_t_min_count": len(req.daily_t_min),
        "input_t_max_count": len(req.daily_t_max),
        "input_date_count": len(req.daily_dates) if req.daily_dates is not None else None,
        # أزواج حرارة (ضمن n) لم تُربَط بتاريخ صالح ⇒ أُسقِطت من السلسلة (لا إخفاء صامت).
        "unmapped_temperature_pairs": n - len(records),
    }
    return records, diagnostics


async def agro_gdd(req: GddProductRequest = Body(...)):
    """منتج GDD — **View تراكميّ مُشتقّ من سلسلة طقس يوميّة canonical** (WX-10.4).

    الانعكاس المعماريّ: GDD تراكم فوق سلسلة أيّام canonical (لا لقطة واحدة). النواة
    (``gdd_agro_product``) تبقى سلطة التراكم حرفيّاً ⇒ عقد GDD القديم byte-compatible
    (``daily_gdd``/``accumulated_gdd``/``thresholds_used``/``valid_period``/``quality_status``/
    قيد عدم تطابق الطول). يُضاف نَسَب تراكميّ (``gdd_lineage_id`` مستقلّ عن آخر يوم ·
    ``contributing_state_ids``) + **تغطية مفصولة عن جودة البيانات** (``coverage``) +
    ``diagnostics`` + ``series_quality_status``. نقيّ حتميّ ⇒ لا 5xx.

    **حفظ byte-compat:** المسار القديم (بلا daily_dates) يُمرّر المصفوفتين **الأصليّتين**
    للنواة (تراها بأطوالها الأصليّة ⇒ قيد mismatch محفوظ)؛ المسار المؤرَّخ تراها من السلسلة
    بعد التطبيع/إزالة التكرار.
    """
    records, diagnostics = _gdd_daily_records(req)
    series = build_canonical_daily_series(records, timezone=req.timezone)
    kernel_kwargs: dict = {}
    if not req.daily_dates:  # المسار القديم: النواة ترى المصفوفتين الأصليّتين (حفظ الطول)
        kernel_kwargs = {
            "kernel_daily_t_min": req.daily_t_min,
            "kernel_daily_t_max": req.daily_t_max,
        }
    return gdd_view(
        series,
        base_c=req.base_c,
        upper_cutoff_c=req.upper_cutoff_c,
        method=req.method,
        period_start=req.start_date,
        period_end=req.end_date,
        reset_policy=req.reset_policy,
        diagnostics=diagnostics,
        **kernel_kwargs,
    )


class CanonicalWeatherStateRequest(BaseModel):
    """مدخلات CanonicalWeatherState (WX-10.1) — متّجه طقس واحد + سياسة GDD اختياريّة.

    الحالة تُجمَّع من منتجات المحرّك القائمة بلا إعادة حساب. الحقول المفقودة ⇒ خانتها
    غير متوفّرة في `availability` + قيد (لا اختلاق). `valid_time` = وقت صلاحيّة اللقطة كما
    يصرّح به المُستهلِك (نَسَب، لا ساعة مُختلقة).
    """

    t_max_c: float | None = None
    t_min_c: float | None = None
    t_mean_c: float | None = None
    rh_mean_pct: float | None = None
    dew_point_c: float | None = None
    wind_2m_ms: float | None = None
    solar_rad_mj_m2: float | None = None
    lat_deg: float | None = None
    elevation_m: float | None = None
    day_of_year: int | None = None
    gdd_daily_t_min: list[float | None] = []
    gdd_daily_t_max: list[float | None] = []
    gdd_base_c: float | None = None
    gdd_upper_cutoff_c: float | None = None
    gdd_method: str = "modified"
    gdd_start_date: str | None = None
    gdd_end_date: str | None = None
    valid_time: str | None = None


def _build_state(req: CanonicalWeatherStateRequest) -> dict:
    return build_canonical_weather_state(
        t_max_c=req.t_max_c,
        t_min_c=req.t_min_c,
        t_mean_c=req.t_mean_c,
        rh_mean_pct=req.rh_mean_pct,
        dew_point_c=req.dew_point_c,
        wind_2m_ms=req.wind_2m_ms,
        solar_rad_mj_m2=req.solar_rad_mj_m2,
        lat_deg=req.lat_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
        gdd_daily_t_min=req.gdd_daily_t_min,
        gdd_daily_t_max=req.gdd_daily_t_max,
        gdd_base_c=req.gdd_base_c,
        gdd_upper_cutoff_c=req.gdd_upper_cutoff_c,
        gdd_method=req.gdd_method,
        gdd_start_date=req.gdd_start_date,
        gdd_end_date=req.gdd_end_date,
        valid_time=req.valid_time,
    )


async def agro_canonical_state(req: CanonicalWeatherStateRequest = Body(...)):
    """WX-10.1 — نقطة قراءة CanonicalWeatherState (الحقيقة الوحيدة للطقس).

    State Product يجمع منتجات المحرّك (ET0/VPD/GDD/astronomy/DTR) في غلاف موحَّد
    (state_id/state_version/schema_version/owner/source_snapshot_id/quality/availability/
    confidence/provenance/evidence/limitations). نقيّ حتميّ fail-closed ⇒ لا 5xx. الخانات
    غير المجموعة في هذا الإنكرمنت مُصرَّحة غيرَ متوفّرة صراحةً (لا ادّعاء تغطية).
    """
    return _build_state(req)


async def agro_weather_state_report(req: CanonicalWeatherStateRequest = Body(...)):
    """WX-10.1 — مستهلك إثبات التصميم: تقرير مُشتقّ **يقرأ الحالة فقط** لا المحرّك.

    يبني CanonicalWeatherState ثمّ يمرّره لـ`weather_state_report` الذي يقرأ الغلاف
    (availability/quality/النَّسَب) دون استدعاء أيّ نواة — إثبات الانعكاس المعماريّ على View
    واحد. يحمل `state_id`/`source_snapshot_id` للنَّسَب (lineage).
    """
    return weather_state_report(_build_state(req))


async def tile_data(
    z: int,
    x: int,
    y: int,
    layer: str = "temperature",
    time: str = "now",
    model: str = "best_match",
    interpolation: Literal["center", "grid"] = "center",
):
    if z < 0 or z > 18:
        raise HTTPException(status_code=400, detail="z outside 0..18")
    if x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        raise HTTPException(status_code=400, detail="x/y outside tile range")
    if layer not in ALLOWED_LAYERS:
        raise HTTPException(status_code=400, detail=f"unsupported layer: {layer}")
    time, model = validate_time_model(time, model)
    lat, lon = tile_center(z, x, y)
    interpolation_payload = None
    # Neutral-tile guarantee: a total upstream failure with no cache must NOT 500/flood
    # the map with errors per tile. Return a neutral tile (value=null, 200) instead —
    # honest "unavailable" state, not a fabricated value. (Stale cache still wins via
    # _cached_sample's own stale_fallback path.)
    try:
        sample, cache_state, cache_age_s, upstream_error = await _cached_sample(
            lat, lon, time, model, f"tile:{z}:{x}:{y}"
        )
    except Exception as exc:  # noqa: BLE001 — upstream down + no cache ⇒ neutral tile
        sample, cache_state, cache_age_s, upstream_error = None, "unavailable", 0, str(exc)
    if interpolation == "grid":
        points = []
        for pt in tile_interpolation_points(z, x, y):
            try:
                s, state, age, err = await _cached_sample(
                    pt["lat"], pt["lon"], time, model, f"tile-grid:{z}:{x}:{y}:{pt['name']}"
                )
                points.append(
                    {
                        **pt,
                        "value": derived_layer_value(layer, s),
                        "sample": s,
                        "cache_state": state,
                        "cache_age_s": age,
                        "upstream_error": err,
                    }
                )
            except Exception as exc:
                points.append({**pt, "value": None, "error": str(exc)})
        interpolation_payload = {"mode": "grid", "points": points}
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": layer,
        "value": derived_layer_value(layer, sample),
        "unit": unit_for_layer(layer),
        "sample": sample,
        "time": time,
        "model": model,
        "source": "open-meteo+sahool-rules",
        "rendered_by": "sahool-client-gridlayer",
        "cache_state": cache_state,
        "cache_age_s": cache_age_s,
        "upstream_error": upstream_error,
        "interpolation": interpolation_payload,
    }


async def operation_tile_data(
    z: int,
    x: int,
    y: int,
    operation: Literal[
        "spraying", "harvesting", "sowing", "fertilizing", "irrigation"
    ] = "spraying",
    time: str = "now",
    model: str = "best_match",
    interpolation: Literal["center", "grid"] = "center",
):
    payload = await tile_data(
        z=z, x=x, y=y, layer="temperature", time=time, model=model, interpolation=interpolation
    )
    decision = operation_suitability(payload["sample"], operation)
    payload.update(
        {
            "layer": f"operation_{operation}",
            "value": decision["score"],
            "unit": "score",
            "operation": decision,
            "source": "open-meteo+sahool-rules",
        }
    )
    return payload


async def tile_series(
    z: int,
    x: int,
    y: int,
    layer: str = "precipitation",
    hours: str = "0,1,3,6,12,24,48",
    model: str = "best_match",
):
    frames = []
    errors: list[str] = []
    for h in parse_series_hours(hours):
        t = time_key_from_hour(h)
        try:
            payload = await tile_data(z=z, x=x, y=y, layer=layer, time=t, model=model)
            frames.append(
                {
                    "hour_offset": h,
                    "time": t,
                    "weather_time": payload.get("sample", {}).get("time"),
                    "value": payload.get("value"),
                    "sample": payload.get("sample"),
                    "cache_state": payload.get("cache_state"),
                    "cache_age_s": payload.get("cache_age_s"),
                    "upstream_error": payload.get("upstream_error"),
                }
            )
        except Exception as exc:
            errors.append(f"{t}: {exc}")
    if not frames:
        raise HTTPException(status_code=502, detail="Open-Meteo tile-series unavailable")
    lat, lon = tile_center(z, x, y)
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": layer,
        "frames": frames,
        "model": model,
        "source": "open-meteo",
        "rendered_by": "sahool-client-gridlayer",
        "partial": bool(errors),
        "upstream_errors": errors[:6],
    }


async def wind_grid(z: int, x: int, y: int, time: str = "now", model: str = "best_match"):
    payload = await tile_data(
        z=z, x=x, y=y, layer="wind", time=time, model=model, interpolation="grid"
    )
    return {**payload, "layer": "wind", "wind_grid": payload.get("interpolation")}


def tile_cache_stats():
    return cache_stats()
