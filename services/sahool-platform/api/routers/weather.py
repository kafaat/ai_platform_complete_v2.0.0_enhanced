"""api/routers/weather.py — الطقس (Weather: current/forecast/historical)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

ملاحظة: مسارات ``/api/v1/automation/weather/*`` مُستخرَجة سلفاً في
``routers/automation.py`` — هنا فقط مسارات ``/api/v1/weather/*``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


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
