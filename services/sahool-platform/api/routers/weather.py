"""api/routers/weather.py — الطقس (Weather: current/forecast/historical)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

ملاحظة: مسارات ``/api/v1/automation/weather/*`` مُستخرَجة سلفاً في
``routers/automation.py`` — هنا فقط مسارات ``/api/v1/weather/*``.
"""

from __future__ import annotations

from math import atan, degrees, pi, sinh
from time import monotonic
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


# Cache صغير للبلاطات؛ يقلل طلبات Open-Meteo أثناء التحريك/التكبير.
_WEATHER_TILE_CACHE: dict[str, tuple[float, dict]] = {}
_WEATHER_TILE_CACHE_TTL_S = 600.0


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

    lat, lon = _tile_center(z, x, y)
    key = f"{z}:{x}:{y}:{time}:{model}"
    now = monotonic()
    cached = _WEATHER_TILE_CACHE.get(key)
    if cached and now - cached[0] < _WEATHER_TILE_CACHE_TTL_S:
        sample = cached[1]
    else:
        try:
            from api.connectors.openmeteo import fetch_weather_tile_data

            sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
            _WEATHER_TILE_CACHE[key] = (now, sample)
            # منع نمو الذاكرة بلا حد أثناء التحريك الطويل.
            if len(_WEATHER_TILE_CACHE) > 2048:
                oldest = sorted(_WEATHER_TILE_CACHE.items(), key=lambda kv: kv[1][0])[:512]
                for old_key, _ in oldest:
                    _WEATHER_TILE_CACHE.pop(old_key, None)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Open-Meteo tile-data: {e}") from e

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
    lat, lon = _tile_center(z, x, y)
    key = f"op:{operation}:{z}:{x}:{y}:{time}:{model}"
    now = monotonic()
    cached = _WEATHER_TILE_CACHE.get(key)
    if cached and now - cached[0] < _WEATHER_TILE_CACHE_TTL_S:
        sample = cached[1]
    else:
        try:
            from api.connectors.openmeteo import fetch_weather_tile_data

            sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
            _WEATHER_TILE_CACHE[key] = (now, sample)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Open-Meteo operation tile-data: {e}"
            ) from e
    decision = _operation_suitability(sample, operation)
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
    }


@router.get("/api/v1/weather/probe")
async def weather_probe(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: str = Query("now"),
    model: str = Query("best_match"),
):
    """قراءة نقطة تحت المؤشر/النقرة + قرارات زراعية مختصرة."""
    try:
        from api.connectors.openmeteo import fetch_weather_tile_data

        sample = await fetch_weather_tile_data(lat, lon, time_key=time, model=model)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo probe: {e}") from e
    operations = {
        op: _operation_suitability(sample, op)
        for op in ["spraying", "harvesting", "sowing", "irrigation"]
    }
    return {
        "location": {"lat": lat, "lon": lon},
        "time": time,
        "model": model,
        "sample": sample,
        "operations": operations,
        "source": "open-meteo+sahool-rules",
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
    """سلسلة زمنية مختصرة للبلاطة نفسها لاستخدام animation/time slider.

    ترجع عينات متعددة لنفس البلاطة عبر مفاتيح +Nh. الواجهة تستطيع تشغيلها
    كتحريك للهطول/الرياح دون طلب مزود صور خارجي.
    """
    if z < 0 or z > 18:
        raise HTTPException(status_code=400, detail="z خارج النطاق 0..18")
    max_tile = 2**z
    if x < 0 or y < 0 or x >= max_tile or y >= max_tile:
        raise HTTPException(status_code=400, detail="x/y خارج نطاق البلاطات لهذا التكبير")
    if layer not in _ALLOWED_WEATHER_TILE_LAYERS:
        raise HTTPException(status_code=400, detail=f"طبقة غير مدعومة: {layer}")
    lat, lon = _tile_center(z, x, y)
    offsets: list[int] = []
    for raw in hours.split(","):
        try:
            offsets.append(max(0, min(72, int(raw.strip()))))
        except ValueError:
            continue
    if not offsets:
        offsets = [0, 1, 3, 6, 12, 24]
    frames = []
    try:
        from api.connectors.openmeteo import fetch_weather_tile_data

        for h in offsets[:12]:
            time_key = "now" if h == 0 else f"+{h}h"
            sample = await fetch_weather_tile_data(lat, lon, time_key=time_key, model=model)
            frames.append(
                {
                    "time": time_key,
                    "value": _safe_layer_value(layer, sample),
                    "sample": sample,
                }
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo tile-series: {e}") from e
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": layer,
        "frames": frames,
        "model": model,
        "source": "open-meteo",
        "rendered_by": "sahool-client-gridlayer",
    }
