"""api/routers/weather.py — الطقس (Weather: current/forecast/historical)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

ملاحظة: مسارات ``/api/v1/automation/weather/*`` مُستخرَجة سلفاً في
``routers/automation.py`` — هنا فقط مسارات ``/api/v1/weather/*``.
"""

from __future__ import annotations

from collections import Counter
from math import atan, degrees, pi, sinh
from time import monotonic
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.service_token_auth import _require_service_token

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
_ALLOWED_WEATHER_TIMES = {"now", "+1h", "+3h", "+6h", "+12h", "+24h", "+48h"}
_ALLOWED_WEATHER_MODELS = {"best_match", "auto", "gfs_seamless", "ecmwf_ifs04"}


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
    sample, cache_state, cache_age_s = _cache_get(key)
    upstream_error = None
    if cache_state == "fresh" and sample is not None:
        return sample, cache_state, cache_age_s, upstream_error
    try:
        from api.connectors.openmeteo import fetch_weather_tile_data

        sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
        _cache_set(key, sample)
        return sample, "refreshed", 0, None
    except Exception as e:
        upstream_error = str(e)
        stale_sample, stale_state, stale_age = _cache_get(key)
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
    if layer == "soil_moisture":
        return sample.get("soil_moisture_1_to_3cm_m3m3") or sample.get(
            "soil_moisture_0_to_1cm_m3m3"
        )
    if layer == "pressure":
        return sample.get("pressure_msl_hpa")
    if layer == "clouds":
        return sample.get("cloud_cover_pct")
    return sample.get("temperature_2m_c")


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


@router.get("/api/v1/weather/current")
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


@router.get("/api/v1/weather/forecast")
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


@router.get("/api/v1/weather/historical")
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
        ],
        "cache": {
            "ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
            "stale_ttl_s": int(_WEATHER_TILE_STALE_TTL_S),
            "max_items_soft": 2048,
        },
        "decision_endpoints": [
            "/api/v1/weather/probe",
            "/api/v1/weather/operation-window",
            "/api/v1/weather/operation-plan",
            "/api/v1/weather/field-weather-summary",
        ],
        "observability_endpoints": [
            "/api/v1/weather/health",
            "/api/v1/weather/readyz",
            "/api/v1/weather/self-test",
            "/api/v1/weather/tile-cache/stats",
            "/api/v1/weather/tile-cache/prune",
            "/api/v1/weather/observability",
            "/api/v1/weather/metrics.prom",
        ],
    }


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
        },
    }


@router.get("/api/v1/weather/metrics.prom")
def weather_metrics_prometheus():
    """Prometheus/OpenMetrics compatible text export for the weather engine.

    لا يستدعي Open‑Meteo ولا يكشف أسراراً؛ الهدف ربط Grafana/Prometheus أو
    فحص سريع من Docker/Kubernetes بدون إضافة تبعية prometheus_client.
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
    كي لا يستطيع مجهول إجبار إفراغ الكاش (تضخيم طلبات Open-Meteo). بقيّة نقاط الطقس
    عامّة (قراءة بإحداثيّات بلا بيانات مستأجِر)؛ هذه وحدها تُغيّر حالة الخادم.
    """
    result = _prune_weather_cache(expired_only=expired_only)
    _record_weather_observation("tile-cache-prune", cache_state="served")
    return result


@router.get("/api/v1/weather/tile-data/{z}/{x}/{y}")
async def weather_tile_data(
    z: int,
    x: int,
    y: int,
    layer: str = Query(
        "temperature",
        description="temperature|wind|precipitation|et0|vpd|soil_temperature|soil_moisture|pressure|clouds",
    ),
    time: str = Query("now", description="now|+1h|+3h|+6h|+12h|+24h|+48h"),
    model: str = Query("best_match", description="best_match أو نموذج Open-Meteo صريح عند الحاجة"),
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
    key = f"{z}:{x}:{y}:{time}:{model}"
    sample, cache_state, cache_age_s = _cache_get(key)
    upstream_error = None
    if cache_state != "fresh":
        try:
            from api.connectors.openmeteo import fetch_weather_tile_data

            sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
            _cache_set(key, sample)
            cache_state = "refreshed"
            cache_age_s = 0
        except Exception as e:
            upstream_error = str(e)
            # إن وجدت عينة stale، نعيدها بدل كسر الخريطة أثناء انقطاع Open‑Meteo.
            stale_sample, stale_state, stale_age = _cache_get(key)
            if stale_sample is None or stale_state not in {"stale", "fresh"}:
                raise HTTPException(status_code=502, detail=f"Open-Meteo tile-data: {e}") from e
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
        "unit": {
            "temperature": "°C",
            "wind": "km/h",
            "precipitation": "mm",
            "et0": "mm",
            "vpd": "kPa",
            "soil_temperature": "°C",
            "soil_moisture": "m³/m³",
            "pressure": "hPa",
            "clouds": "%",
        }.get(layer, ""),
        "sample": sample,
        "time": time,
        "model": model,
        "source": "open-meteo",
        "rendered_by": "sahool-client-gridlayer",
        "cache_ttl_s": int(_WEATHER_TILE_CACHE_TTL_S),
        "cache_state": cache_state,
        "cache_age_s": cache_age_s,
        "upstream_error": upstream_error,
    }


@router.get("/api/v1/weather/operation-tile-data/{z}/{x}/{y}")
async def weather_operation_tile_data(
    z: int,
    x: int,
    y: int,
    operation: Literal["spraying", "harvesting", "sowing", "irrigation"] = Query("spraying"),
    time: str = Query("now"),
    model: str = Query("best_match"),
):
    """بلاطة صلاحية عملية زراعية؛ Open-Meteo بيانات، SAHOOL قرار ورسم."""
    if z < 0 or z > 18:
        raise HTTPException(status_code=400, detail="z خارج النطاق 0..18")
    max_tile = 2**z
    if x < 0 or y < 0 or x >= max_tile or y >= max_tile:
        raise HTTPException(status_code=400, detail="x/y خارج نطاق البلاطات لهذا التكبير")
    time, model = _validate_time_model(time, model)
    lat, lon = _tile_center(z, x, y)
    key = f"op:{operation}:{z}:{x}:{y}:{time}:{model}"
    sample, cache_state, cache_age_s = _cache_get(key)
    upstream_error = None
    if cache_state != "fresh":
        try:
            from api.connectors.openmeteo import fetch_weather_tile_data

            sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
            _cache_set(key, sample)
            cache_state = "refreshed"
            cache_age_s = 0
        except Exception as e:
            upstream_error = str(e)
            stale_sample, stale_state, stale_age = _cache_get(key)
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
    }


@router.get("/api/v1/weather/probe")
async def weather_probe(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: str = Query("now"),
    model: str = Query("best_match"),
):
    """قراءة نقطة تحت المؤشر/النقرة + قرارات زراعية مختصرة."""
    time, model = _validate_time_model(time, model)
    key = f"probe:{round(lat, 4)}:{round(lon, 4)}:{time}:{model}"
    sample, cache_state, cache_age_s = _cache_get(key)
    upstream_error = None
    if cache_state != "fresh":
        try:
            from api.connectors.openmeteo import fetch_weather_tile_data

            sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
            _cache_set(key, sample)
            cache_state = "refreshed"
            cache_age_s = 0
        except Exception as e:
            upstream_error = str(e)
            stale_sample, stale_state, stale_age = _cache_get(key)
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


@router.get("/api/v1/weather/operation-window")
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


@router.get("/api/v1/weather/field-weather-summary")
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


@router.get("/api/v1/weather/operation-plan")
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


@router.get("/api/v1/weather/tile-series/{z}/{x}/{y}")
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
