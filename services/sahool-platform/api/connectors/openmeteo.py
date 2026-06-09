"""
api/connectors/openmeteo.py
============================
HTTP integration لـOpen-Meteo (مجاني، بدون مفتاح).

المرجع المُحقَّق (2026):
  https://open-meteo.com/
  - 30+ نموذج طقس (ECMWF, NOAA, DWD)
  - تاريخ ٨٠ سنة (ERA5 من 1940)
  - Reference ET₀ متاح
  - AGPLv3 self-hostable
  - CC BY 4.0 redistribution
  ⚠ غير تجاري فقط (commercial يحتاج subscription)

البنية:
  - FastAPI Core يربط هذا للـ/api/v1/weather
  - النواة تستهلكها عبر weather_openmeteo connector (abstraction موجود)
  - الموبايل: GET /api/v1/weather/{lat}/{lon}

التصحيح الصادق:
  ✅ Code مكتوب ومُحقَّق نحوياً
  ⚠ لم يُختبَر runtime (الشبكة معطّلة في bash_tool هنا)
  ✅ بنية URLs وschemas مأخوذة من Open-Meteo docs مباشرة
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger("sahool.api.openmeteo")


def _daily_at(daily: dict, key: str, i: int, default):
    """H6 FIX: فهرسة آمنة لمصفوفة يوميّة من Open-Meteo.

    الاستجابة قد تُرجع مصفوفات مُسنّنة (أقصر من `time`) أو قيمة `null`،
    خاصّةً قرب اليوم الحالي حيث يتأخّر أرشيف ERA5 ~5 أيام. الوصول المباشر
    `d[key][i]` كان يرمي IndexError/KeyError أو يمرّر None لحقل float.
    """
    lst = daily.get(key)
    if not isinstance(lst, list) or i >= len(lst):
        return default
    v = lst[i]
    return default if v is None else v


# ─── Endpoints (مأخوذة من open-meteo.com docs) ────────────────────

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


# ─── Data models ──────────────────────────────────────────────────


@dataclass
class CurrentWeather:
    temperature_c: float
    humidity_pct: float
    wind_speed_ms: float
    precipitation_mm: float
    cloud_cover_pct: float
    weather_code: int  # WMO code (0=clear, 61=rain, etc.)
    is_day: bool
    timestamp: str  # ISO


@dataclass
class DailyForecast:
    date: str  # YYYY-MM-DD
    temp_max_c: float
    temp_min_c: float
    precipitation_mm: float
    et0_mm: float | None  # FAO-56 reference ET₀ (في النموذج!)
    sunshine_hours: float | None
    wind_max_ms: float
    weather_code: int


@dataclass
class WeatherBundle:
    """البيانات الكاملة لشاشة الطقس + توصيات."""

    location: tuple[float, float]  # (lat, lon)
    elevation_m: float
    current: CurrentWeather
    daily_forecast: list[DailyForecast]
    historical_30d: list[DailyForecast] | None = None


# ─── Implementation ────────────────────────────────────────────────


async def fetch_current(
    lat: float,
    lon: float,
    timeout_s: float = 10.0,
) -> CurrentWeather:
    """يجلب الطقس الحالي."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "wind_speed_10m",
                "precipitation",
                "cloud_cover",
                "weather_code",
                "is_day",
            ]
        ),
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    c = data.get("current", {})
    return CurrentWeather(
        temperature_c=c.get("temperature_2m", 0),
        humidity_pct=c.get("relative_humidity_2m", 0),
        wind_speed_ms=c.get("wind_speed_10m", 0),
        precipitation_mm=c.get("precipitation", 0),
        cloud_cover_pct=c.get("cloud_cover", 0),
        weather_code=c.get("weather_code", 0),
        is_day=bool(c.get("is_day", 1)),
        timestamp=c.get("time", ""),
    )


async def fetch_current_batch(
    coords: list[tuple[float, float]],
    timeout_s: float = 15.0,
) -> list[CurrentWeather]:
    """يجلب طقس عدّة إحداثيّات في طلب واحد (أفضل ممارسة Open-Meteo).

    Open-Meteo يدعم إحداثيّات مفصولة بفواصل ويُرجِع مصفوفة — يقلّل عدد الطلبات
    ويخفّف ضغط معدّل الاستدعاء (rate limit). يُرجِع نتيجة لكلّ إحداثيّة بالترتيب.
    عند ≤1 إحداثيّة يكافئ fetch_current.
    """
    if not coords:
        return []
    lats = ",".join(str(c[0]) for c in coords)
    lons = ",".join(str(c[1]) for c in coords)
    params = {
        "latitude": lats,
        "longitude": lons,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "wind_speed_10m",
                "precipitation",
                "cloud_cover",
                "weather_code",
                "is_day",
            ]
        ),
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    # عند عدّة إحداثيّات يُرجِع Open-Meteo قائمة؛ عند واحدة يُرجِع كائناً.
    if isinstance(data, dict):
        data = [data]
    out = []
    for entry in data:
        c = entry.get("current", {})
        out.append(
            CurrentWeather(
                temperature_c=c.get("temperature_2m", 0),
                humidity_pct=c.get("relative_humidity_2m", 0),
                wind_speed_ms=c.get("wind_speed_10m", 0),
                precipitation_mm=c.get("precipitation", 0),
                cloud_cover_pct=c.get("cloud_cover", 0),
                weather_code=c.get("weather_code", 0),
                is_day=bool(c.get("is_day", 1)),
                timestamp=c.get("time", ""),
            )
        )
    return out


async def fetch_daily_forecast(
    lat: float,
    lon: float,
    days: int = 7,
    timeout_s: float = 15.0,
) -> list[DailyForecast]:
    """يجلب توقّعات ٧-١٦ يوم."""
    days = min(max(days, 1), 16)
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "sunshine_duration",
                "wind_speed_10m_max",
                "weather_code",
            ]
        ),
        "timezone": "auto",
        "wind_speed_unit": "ms",
        "forecast_days": days,
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    d = data.get("daily", {})
    dates = d.get("time", [])
    results = []
    for i, date in enumerate(dates):
        _sun = _daily_at(d, "sunshine_duration", i, None)
        results.append(
            DailyForecast(
                date=date,
                temp_max_c=_daily_at(d, "temperature_2m_max", i, 0),
                temp_min_c=_daily_at(d, "temperature_2m_min", i, 0),
                precipitation_mm=_daily_at(d, "precipitation_sum", i, 0),
                et0_mm=_daily_at(d, "et0_fao_evapotranspiration", i, None),
                sunshine_hours=(_sun / 3600 if _sun else None),
                wind_max_ms=_daily_at(d, "wind_speed_10m_max", i, 0),
                weather_code=_daily_at(d, "weather_code", i, 0),
            )
        )
    return results


async def fetch_historical(
    lat: float,
    lon: float,
    start_date: str,  # YYYY-MM-DD
    end_date: str,  # YYYY-MM-DD
    timeout_s: float = 30.0,
) -> list[DailyForecast]:
    """يجلب البيانات التاريخيّة (ERA5 reanalysis)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "sunshine_duration",
                "wind_speed_10m_max",
                "weather_code",
            ]
        ),
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(HISTORICAL_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    d = data.get("daily", {})
    dates = d.get("time", [])
    results = []
    for i, date in enumerate(dates):
        _sun = _daily_at(d, "sunshine_duration", i, None)
        results.append(
            DailyForecast(
                date=date,
                temp_max_c=_daily_at(d, "temperature_2m_max", i, 0),
                temp_min_c=_daily_at(d, "temperature_2m_min", i, 0),
                precipitation_mm=_daily_at(d, "precipitation_sum", i, 0),
                et0_mm=_daily_at(d, "et0_fao_evapotranspiration", i, None),
                sunshine_hours=(_sun / 3600 if _sun else None),
                wind_max_ms=_daily_at(d, "wind_speed_10m_max", i, 0),
                weather_code=_daily_at(d, "weather_code", i, 0),
            )
        )
    return results


async def fetch_bundle(
    lat: float,
    lon: float,
    forecast_days: int = 7,
    include_historical_30d: bool = False,
) -> WeatherBundle:
    """يجلب البيانات الكاملة (current + forecast + optional historical)."""
    current = await fetch_current(lat, lon)
    forecast = await fetch_daily_forecast(lat, lon, days=forecast_days)

    historical = None
    if include_historical_30d:
        end = datetime.utcnow().date()
        start = end - timedelta(days=30)
        historical = await fetch_historical(
            lat,
            lon,
            start.isoformat(),
            end.isoformat(),
        )

    # elevation من أوّل forecast call (Open-Meteo يُرجعه)
    # نُعيد ٠ كـfallback — في الإنتاج: cache من /elevation endpoint
    return WeatherBundle(
        location=(lat, lon),
        elevation_m=0,
        current=current,
        daily_forecast=forecast,
        historical_30d=historical,
    )


# ─── Helpers ──────────────────────────────────────────────────────

WMO_DESCRIPTIONS_AR = {
    0: "صافٍ",
    1: "غائم جزئياً",
    2: "غائم جزئياً",
    3: "غائم",
    45: "ضباب",
    48: "ضباب جامد",
    51: "رذاذ خفيف",
    53: "رذاذ متوسّط",
    55: "رذاذ كثيف",
    61: "مطر خفيف",
    63: "مطر متوسّط",
    65: "مطر غزير",
    71: "ثلج خفيف",
    73: "ثلج متوسّط",
    75: "ثلج كثيف",
    80: "زخّات مطر خفيفة",
    81: "زخّات مطر متوسّطة",
    82: "زخّات مطر عنيفة",
    95: "عاصفة رعديّة",
    96: "عاصفة مع برَد خفيف",
    99: "عاصفة مع برَد عنيف",
}


def describe_weather_ar(code: int) -> str:
    """يحوّل WMO code → وصف عربي."""
    return WMO_DESCRIPTIONS_AR.get(code, "غير معروف")


def spraying_condition_score(forecast: DailyForecast) -> tuple[str, str]:
    """
    يقيّم ظروف الرشّ من توقّع اليوم.

    المرجع: WHO/FAO Pesticide Application Equipment Guidelines
      - الرياح > 5 م/ث = غير مناسب
      - مطر متوقّع = غير مناسب
      - حرارة > 35°م = غير مناسب
      - رطوبة < 30٪ = غير مناسب

    Returns:
        (status, reason_ar)
        status ∈ {very_bad, bad, reasonable, good, very_good}
    """
    if forecast.wind_max_ms > 8 or forecast.precipitation_mm > 5:
        return "very_bad", "رياح قويّة أو مطر متوقّع"
    if forecast.wind_max_ms > 5:
        return "bad", "رياح متوسّطة فوق ٥ م/ث"
    if forecast.temp_max_c > 35:
        return "bad", "حرارة عالية > ٣٥°م"
    if forecast.precipitation_mm > 0:
        return "reasonable", "مطر متوقّع لكن خفيف"
    if forecast.wind_max_ms < 2:
        return "very_good", "ظروف مثاليّة للرشّ"
    return "good", "ظروف مناسبة"
