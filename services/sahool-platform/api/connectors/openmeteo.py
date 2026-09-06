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
from datetime import UTC, datetime, timedelta

import httpx
from core.circuit_breaker import CircuitBreaker

logger = logging.getLogger("sahool.api.openmeteo")


# ─── قاطع الدائرة (circuit breaker) ────────────────────────────────
#
# قاطع واحد مشترك لكامل خدمة Open-Meteo. الاختيار: قاطع لكلّ الخدمة لا لكلّ
# نقطة نهاية، لأنّ الـforecast والـarchive والـgeocoding تشترك في نفس البنية
# التحتيّة الخلفيّة؛ سقوط أحدها مؤشّر على عطل مشترك، والعزل على مستوى الخدمة
# يعطي fail-fast أوضح وأبسط للرصد. عتبات محافظة: ٥ إخفاقات متتالية تفتح
# القاطع، ٣٠ ثانية تبريد، ونجاح واحد في HALF_OPEN يُعيد الإغلاق.
_OPENMETEO_BREAKER = CircuitBreaker(
    name="openmeteo",
    failure_threshold=5,
    recovery_timeout_s=30.0,
    success_threshold=1,
)

# أنواع الأعطال التي يعدّها الموصِّل فشلاً «منبعيّاً» (upstream) — وهي ذاتها
# ما يرفعه الموصِّل أصلاً: أخطاء شبكة/مهلة (RequestError) ورموز HTTP ≥4xx/5xx
# (HTTPStatusError من raise_for_status). الحالات التجاريّة (٤٠٤ منطقيّ، نتيجة
# فارغة) لا تمرّ هنا لأنّ الموصِّل لا يرفعها كفشل أصلاً.
_UPSTREAM_ERRORS = (httpx.HTTPStatusError, httpx.RequestError)

# WEATHER-MODEL-IDENTITY-v1 — ليس كلُّ 4xx عطلَ مزوّد. رفضُ **طلبنا** (معرّفُ
# نموذجٍ متقاعد، معامِلٌ مجهول ⇒ 400/404/422) لا يقول شيئاً عن توافر Open-Meteo،
# وكان يُحسَب على القاطع المشترك: مستخدمٌ يختار نموذجاً مرفوضاً خمسَ مرّات كان
# يُطفئ الطقسَ للجميع ٣٠ ثانية. و401/403/429 حالةُ **وصولٍ** (إعدادٌ/حصّة) تُرى
# على حدة. كلاهما يُسجَّل ويُعاد رفعُه كما هو — نوعُ الاستثناء للمتّصلين لم يتغيّر.
_ACCESS_STATUS_CODES = frozenset({401, 403, 429})
_last_request_error: dict | None = None
_last_access_error: dict | None = None


def classify_upstream_error(exc: Exception) -> str:
    """``provider`` (شبكة/مهلة/5xx ⇒ قاطع) · ``access`` (401/403/429) · ``request`` (بقيّة 4xx)."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in _ACCESS_STATUS_CODES:
            return "access"
        if 400 <= code < 500:
            return "request"
    return "provider"


def _upstream_reason(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 — جسمٌ غيرُ JSON: لا سبب، لا انهيار
        return None
    reason = body.get("reason") if isinstance(body, dict) else None
    return str(reason)[:200] if reason else None


def _record_non_provider_error(kind: str, exc: httpx.HTTPStatusError) -> None:
    global _last_request_error, _last_access_error
    record = {
        "status_code": exc.response.status_code,
        "reason": _upstream_reason(exc.response),
    }
    if kind == "access":
        _last_access_error = record
    else:
        _last_request_error = record


def openmeteo_breaker_state() -> dict:
    """إسقاط رصديّ لحالة قاطع Open-Meteo (للـ/healthz/deps والرصد).

    accessor على مستوى الوحدة — لا نقطة نهاية جديدة. يعكس العدّادات الحقيقيّة.
    """
    snap = _OPENMETEO_BREAKER.snapshot()
    snap["last_request_error"] = _last_request_error
    snap["last_access_error"] = _last_access_error
    return snap


# علم «حُذِّر لهذه النافذة»: نُسجّل تحذيراً واحداً عند فتح القاطع لا على كلّ fail-fast.
# تصيير الطقس يُطلِق عشرات بلاطات متزامنة، فكان كلّ fail-fast يُنتِج تحذيراً متطابقاً
# ويُغرِق السجلّ. الآن: WARNING مرّةً لكلّ نافذة فتح، والبقيّة DEBUG، ويُصفَّر العلم
# فور سماح القاطع ثانيةً (تعافٍ) فيُحذَّر مجدّداً إن انفتح من جديد.
_circuit_open_warned = False


def _guard_breaker() -> None:
    """يفشل سريعاً إن كان القاطع مفتوحاً (قبل لمس الشبكة).

    يرفع نفس نوع استثناء العطل المنبعيّ الذي يلتقطه المتّصلون أصلاً
    (httpx.ConnectError ⊂ httpx.RequestError) فيُحفَظ تعاملهم 503. لا يغيّر
    تواقيع الدوالّ العامّة ولا أنواع الاستثناءات التي يلتقطها المتّصلون.
    """
    global _circuit_open_warned
    if not _OPENMETEO_BREAKER.allow():
        snap = _OPENMETEO_BREAKER.snapshot()
        if not _circuit_open_warned:
            _circuit_open_warned = True
            logger.warning(
                "openmeteo.circuit_open fail_fast failures=%s retry_in=%ss "
                "(تحذير واحد لكلّ نافذة فتح؛ تُكتَم بقيّة fail-fast حتى التعافي)",
                snap["consecutive_failures"],
                snap["seconds_until_retry"],
            )
        else:
            logger.debug(
                "openmeteo.circuit_open fail_fast (مكتوم) retry_in=%ss",
                snap["seconds_until_retry"],
            )
        raise httpx.ConnectError(
            "circuit open — Open-Meteo unavailable (fail-fast, "
            f"retry in {snap['seconds_until_retry']}s)"
        )
    # سمح القاطع (مغلق/نصف-مفتوح بعد التبريد) ⇒ صفّر العلم لنافذة الفتح القادمة.
    _circuit_open_warned = False


async def _fetch_json(url: str, params: dict, timeout_s: float):
    """ينفّذ طلب GET ويُرجِع JSON مع لفّ القاطع حول الاستدعاء المنبعيّ.

    - قبل اللمس: إن كان القاطع مفتوحاً ← fail-fast (نفس نوع الاستثناء).
    - عند نجاح الطلب (HTTP 2xx + JSON) ← record_success.
    - عند عطل منبعيّ (شبكة/مهلة/HTTP error) ← record_failure ثم إعادة الرفع
      كما هي، فيبقى سلوك المتّصلين والاستثناءات الملتقَطة دون تغيير.
    """
    _guard_breaker()
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except _UPSTREAM_ERRORS as exc:
        kind = classify_upstream_error(exc)
        if kind == "provider":
            _OPENMETEO_BREAKER.record_failure()
        else:
            _record_non_provider_error(kind, exc)  # type: ignore[arg-type]
        raise
    _OPENMETEO_BREAKER.record_success()
    return data


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


# **المطرُ وحدَه صار `float | None` في هذه الشريحة، والباقي مُعلَنٌ لا منسيّ.**
# العقدُ المطبوع كان يمنع الغياب (`float`) فتختلق الحافّةُ `0` لتفي به — وقيس أثرُ
# ذلك على المطر بالتنفيذ: يُنتِج أمرَ ريٍّ («خلال ٢٤ ساعة») حيث القراءةُ الحقيقيّة
# تقول «لا حاجة». فالمطرُ أُخِذ أوّلاً لأنّ انحيازَه في اتّجاه الإذن ويصل قراراً
# يُنفَّذ على أرض. وبقيّةُ الحقول (`temperature_c` · `humidity_pct` · `temp_max_c` …)
# ما تزال تختلق الصفر، وهي `TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01`
# **مفتوحةً بنطاقٍ مقيس**، لا مُصلَحةً هنا ولا مُدَّعًى إصلاحُها.
@dataclass
class CurrentWeather:
    temperature_c: float
    humidity_pct: float
    wind_speed_ms: float
    wind_direction_deg: float | None
    wind_direction_source: str | None
    wind_gusts_ms: float | None
    precipitation_mm: float | None
    cloud_cover_pct: float
    weather_code: int  # WMO code (0=clear, 61=rain, etc.)
    is_day: bool
    timestamp: str  # ISO


@dataclass
class DailyForecast:
    date: str  # YYYY-MM-DD
    temp_max_c: float
    temp_min_c: float
    precipitation_mm: float | None
    et0_mm: float | None  # FAO-56 reference ET₀ (في النموذج!)
    sunshine_hours: float | None
    wind_max_ms: float
    weather_code: int
    # شمسيّ/نهاريّ — مفيد لجدولة الريّ بالطاقة الشمسيّة (مضخّات شمسيّة) وتقدير
    # الإنتاج الشمسيّ: وقت الشروق/الغروب، مدّة النهار، ومجموع الإشعاع القصير الموجة.
    sunrise: str | None = None  # ISO datetime محلّيّ
    sunset: str | None = None  # ISO datetime محلّيّ
    daylight_hours: float | None = None  # مدّة النهار بالساعات
    solar_radiation_mj_m2: float | None = None  # مجموع الإشعاع القصير الموجة (MJ/m²·يوم)


@dataclass
class WeatherBundle:
    """البيانات الكاملة لشاشة الطقس + توصيات."""

    location: tuple[float, float]  # (lat, lon)
    elevation_m: float
    current: CurrentWeather
    daily_forecast: list[DailyForecast]
    historical_30d: list[DailyForecast] | None = None


# مفاتيح Open-Meteo اليوميّة المطلوبة (مشتركة بين التوقّع والتاريخيّ) — تشمل
# الشروق/الغروب/مدّة النهار/الإشعاع الشمسيّ لجدولة الريّ بالطاقة الشمسيّة.
_DAILY_KEYS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "et0_fao_evapotranspiration",
    "sunshine_duration",
    "wind_speed_10m_max",
    "weather_code",
    "sunrise",
    "sunset",
    "daylight_duration",
    "shortwave_radiation_sum",
]


def _build_daily(d: dict, i: int, date: str) -> DailyForecast:
    """يبني DailyForecast من استجابة Open-Meteo اليوميّة (فهرسة آمنة لكلّ حقل)."""
    # `is not None` لا truthiness: 0 ثانية (سطوع/نهار) قيمة صالحة لا «مفقودة».
    _sun = _daily_at(d, "sunshine_duration", i, None)
    _day = _daily_at(d, "daylight_duration", i, None)
    return DailyForecast(
        date=date,
        temp_max_c=_daily_at(d, "temperature_2m_max", i, 0),
        temp_min_c=_daily_at(d, "temperature_2m_min", i, 0),
        precipitation_mm=_daily_at(d, "precipitation_sum", i, None),
        et0_mm=_daily_at(d, "et0_fao_evapotranspiration", i, None),
        sunshine_hours=(_sun / 3600 if _sun is not None else None),
        wind_max_ms=_daily_at(d, "wind_speed_10m_max", i, 0),
        weather_code=_daily_at(d, "weather_code", i, 0),
        sunrise=_daily_at(d, "sunrise", i, None),
        sunset=_daily_at(d, "sunset", i, None),
        daylight_hours=(round(_day / 3600, 2) if _day is not None else None),
        solar_radiation_mj_m2=_daily_at(d, "shortwave_radiation_sum", i, None),
    )


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
                "wind_direction_10m",
                "wind_gusts_10m",
                "precipitation",
                "cloud_cover",
                "weather_code",
                "is_day",
            ]
        ),
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }

    data = await _fetch_json(FORECAST_URL, params, timeout_s)

    c = data.get("current", {})
    wind_direction = c.get("wind_direction_10m")
    wind_direction_source = "open-meteo" if wind_direction is not None else None
    # احتياط اتّجاه الرياح للحالة الحالية أيضاً: لا نكتفي بالبلاطات. إن غاب
    # الاتجاه من Open-Meteo نحاول MET.no، وإن فشل نبقي القيمة None بصدق.
    if wind_direction is None:
        try:
            from api.connectors import metno_wind

            deg = await metno_wind.fetch_wind_direction_deg(lat, lon)
            if deg is not None:
                wind_direction = deg
                wind_direction_source = "met.no"
        except Exception:  # noqa: BLE001 — الاحتياط لا يكسر الطقس الحالي
            pass
    return CurrentWeather(
        temperature_c=c.get("temperature_2m", 0),
        humidity_pct=c.get("relative_humidity_2m", 0),
        wind_speed_ms=c.get("wind_speed_10m", 0),
        wind_direction_deg=wind_direction,
        wind_direction_source=wind_direction_source,
        wind_gusts_ms=c.get("wind_gusts_10m"),
        precipitation_mm=c.get("precipitation"),
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
                "wind_direction_10m",
                "wind_gusts_10m",
                "precipitation",
                "cloud_cover",
                "weather_code",
                "is_day",
            ]
        ),
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }
    data = await _fetch_json(FORECAST_URL, params, timeout_s)

    # عند عدّة إحداثيّات يُرجِع Open-Meteo قائمة؛ عند واحدة يُرجِع كائناً.
    if isinstance(data, dict):
        data = [data]
    out = []
    for entry in data:
        c = entry.get("current", {})
        # الدفعة (عدّة مواقع) لا تستدعي احتياط MET.no (تفادي N طلبات): اتّجاه Open-Meteo
        # وحده، والمصدر open-meteo إن وُجد وإلّا None (لا قيمة وهميّة).
        wd = c.get("wind_direction_10m")
        out.append(
            CurrentWeather(
                temperature_c=c.get("temperature_2m", 0),
                humidity_pct=c.get("relative_humidity_2m", 0),
                wind_speed_ms=c.get("wind_speed_10m", 0),
                wind_direction_deg=wd,
                wind_direction_source="open-meteo" if wd is not None else None,
                wind_gusts_ms=c.get("wind_gusts_10m"),
                precipitation_mm=c.get("precipitation"),
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
        "daily": ",".join(_DAILY_KEYS),
        "timezone": "auto",
        "wind_speed_unit": "ms",
        "forecast_days": days,
    }

    data = await _fetch_json(FORECAST_URL, params, timeout_s)

    d = data.get("daily", {})
    dates = d.get("time", [])
    return [_build_daily(d, i, date) for i, date in enumerate(dates)]


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
        "daily": ",".join(_DAILY_KEYS),
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }

    data = await _fetch_json(HISTORICAL_URL, params, timeout_s)

    d = data.get("daily", {})
    dates = d.get("time", [])
    return [_build_daily(d, i, date) for i, date in enumerate(dates)]


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
        end = datetime.now(UTC).date()
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


# ─── Weather map tile data (Open-Meteo as data source; SAHOOL renders tiles) ───

_TILE_CURRENT_KEYS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "cloud_cover",
    "pressure_msl",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "weather_code",
    "is_day",
]

_TILE_HOURLY_KEYS = [
    # سنطلب نسخة hourly من المتغيرات الحالية حتى يدعم محرك البلاطات +1h/+3h/+24h
    # دون تغيير واجهة الرسم في Leaflet.
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "cloud_cover",
    "pressure_msl",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "weather_code",
    "vapour_pressure_deficit",
    "et0_fao_evapotranspiration",
    "soil_temperature_0cm",
    "soil_temperature_6cm",
    "soil_temperature_18cm",
    "soil_temperature_54cm",
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "soil_moisture_3_to_9cm",
    "precipitation_probability",
]


def _soil_temperature_10_40cm(t6, t18, t54):
    """Approximate Meteoblue-like 10-40 cm down soil temperature from Open-Meteo depths.

    Open-Meteo exposes 6/18/54 cm soil temperature. For the 10-40 cm agronomic layer,
    use the 18 cm value as the center anchor and blend toward an interpolated ~40 cm
    value when 54 cm is available. This is intentionally labelled as an approximation
    in the API metadata and UI rather than a provider-native Meteoblue tile.
    """
    vals = []
    try:
        if t18 is not None:
            vals.append((float(t18), 0.65))
        if t54 is not None:
            # Linear interpolation between 18 and 54 cm at ~40 cm.
            if t18 is not None:
                t40 = float(t18) + (float(t54) - float(t18)) * ((40 - 18) / (54 - 18))
            else:
                t40 = float(t54)
            vals.append((t40, 0.35))
        elif t6 is not None:
            vals.append((float(t6), 0.20))
    except (TypeError, ValueError):
        return None
    if not vals:
        return None
    total_w = sum(w for _, w in vals)
    return round(sum(v * w for v, w in vals) / total_w, 2)


def _parse_time_offset_hours(time_key: str | None) -> int:
    """يفهم مفاتيح الواجهة: now, +1h, +3h, +24h.

    Open-Meteo يعيد مصفوفات hourly مرتبة من الوقت الحالي. نستخدم أقرب فهرس
    مطلوب بدل الاكتفاء بالساعة الأولى، وبذلك تصبح بلاطات SAHOOL قابلة للتحريك
    زمنياً دون مزوّد tiles خارجي.
    """
    if not time_key or time_key == "now":
        return 0
    raw = str(time_key).strip().lower()
    if raw.startswith("+") and raw.endswith("h"):
        try:
            return max(0, min(72, int(raw[1:-1])))
        except ValueError:
            return 0
    return 0


def _parse_provider_time(value) -> datetime | None:
    """يقرأ طابعَ Open-Meteo (``2026-09-05T13:00`` أو ``…T13:15``)؛ ``None`` لِما لا يُقرأ."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def resolve_hourly_index(times: list | None, anchor_time, offset_hours: int) -> dict:
    """يحلّ ``+Nh`` إلى **فهرسٍ بطابعه الزمنيّ**، لا بموضعه في المصفوفة.

    **العطلان المقيسان اللذان يُغلَقان هنا** (كان ``idx = offset_hours``):

    1. مصفوفاتُ Open-Meteo الساعيّة تبدأ من **منتصف ليل** أوّل يومٍ لا من الساعة
       الحاليّة؛ فـ``+1h`` في الثالثة عصراً كان يُرجِع **01:00 فجراً**.
    2. نموذجٌ خطوتُه ٦ ساعات (AIFS) يُرجِع سلسلةً أخفّ؛ فـ``+6h`` بالموضع كان
       يُرجِع **+36h**، و``+1h`` يُرجِع **+6h**.

    **السياسة مُعلَنة:** المرساةُ ساعةُ ``current.time`` مُدوَّرةً للأسفل؛ الهدفُ
    المرساة + N. مطابقٌ ⇒ ``exact``؛ وإلّا الأقربُ (والأسبقُ عند التعادل) مع
    ``policy="nearest"`` و``delta_hours`` وقيدٌ مسمّى — فلا يُقرأ ``+6h`` على أنّه
    ``+1h`` أبداً. لا مرساة ⇒ ``unanchored`` بلا فهرس.

    **وسقط احتياطُ «أقربِ قيمةٍ غيرِ فارغة»** الذي كان يمسح المصفوفةَ أماماً
    وخلفاً: هو الاستبدالُ الصامتُ نفسُه على مستوى القيمة. ``None`` أصدق.
    نسخةٌ مطابقة في ``services/weather-service/open_meteo.py`` (خدمتان لا
    تتشاركان حزمة).
    """
    out: dict = {
        "requested_offset_hours": int(offset_hours),
        "anchor": None,
        "target": None,
        "resolved": None,
        "index": None,
        "policy": "unanchored",
        "delta_hours": None,
        "limitations": [],
    }
    anchor = _parse_provider_time(anchor_time)
    if anchor is None:
        out["limitations"].append("sampling_anchor_unavailable")
        return out
    anchor = anchor.replace(minute=0, second=0, microsecond=0)
    target = anchor + timedelta(hours=int(offset_hours))
    out["anchor"] = anchor.isoformat(timespec="minutes")
    out["target"] = target.isoformat(timespec="minutes")
    parsed = [(i, _parse_provider_time(t)) for i, t in enumerate(times or [])]
    parsed = [(i, t) for i, t in parsed if t is not None]
    if not parsed:
        out["policy"] = "empty_series"
        out["limitations"].append("hourly_series_empty")
        return out
    for i, t in parsed:
        if t == target:
            out.update(index=i, resolved=str((times or [])[i]), policy="exact", delta_hours=0.0)
            return out
    i, t = min(parsed, key=lambda p: (abs((p[1] - target).total_seconds()), p[1] > target))
    delta = round((t - target).total_seconds() / 3600.0, 2)
    out.update(index=i, resolved=str((times or [])[i]), policy="nearest", delta_hours=delta)
    out["limitations"].append(f"requested_time_not_in_series:nearest_used:delta_hours={delta:+.2f}")
    return out


def _hourly_value_at(hourly: dict, key: str, index: int | None):
    """قيمةُ ``key`` عند فهرسٍ **مُحَلٍّ بالطابع**؛ ``None`` بصدق عند الغياب."""
    values = hourly.get(key)
    if index is None or not isinstance(values, list) or index < 0 or index >= len(values):
        return None
    return values[index]


async def fetch_weather_tile_data(
    lat: float,
    lon: float,
    timeout_s: float = 12.0,
    time_key: str = "now",
    model: str = "best_match",
) -> dict:
    """Open-Meteo نقطة عيّنة واحدة لتغذية بلاطة طقس مرسومة داخل SAHOOL.

    هذه الدالة لا تُرجع صورة ولا تعتمد على tiles خارجية. Open-Meteo هو مصدر
    البيانات فقط، والواجهة/SAHOOL ترسم: heat raster + wind animation + legend.
    نطلب current للمتغيرات السريعة و hourly لأول ساعة متاحة للمتغيرات الزراعية
    التي لا تتوفر دائماً في current مثل ET0/VPD/soil moisture.
    """
    offset_hours = _parse_time_offset_hours(time_key)
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(_TILE_CURRENT_KEYS),
        "hourly": ",".join(_TILE_HOURLY_KEYS),
        "forecast_days": 4,
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    }
    # best_match هو السلوك الافتراضي في Open-Meteo. لا نرسل models إلا عندما يحدد
    # المستخدم نموذجاً صريحاً مدعوماً في البيئة، حتى لا نكسر free/default mode.
    if model and model not in {"best_match", "auto"}:
        params["models"] = model

    data = await _fetch_json(FORECAST_URL, params, timeout_s)
    c = data.get("current", {}) if isinstance(data, dict) else {}
    h = data.get("hourly", {}) if isinstance(data, dict) else {}
    use_current = offset_hours == 0
    # WEATHER-MODEL-IDENTITY-v1: الفهرسُ بالطابع الزمنيّ لا بالموضع.
    resolution = resolve_hourly_index(h.get("time"), c.get("time"), offset_hours)
    if use_current and c.get("time") is not None:
        # مراجعةُ Copilot على #985 (مُعاد إنتاجُها): `time` يُرجَع من `current.time` بدقائقه
        # بينما كان `resolved` صفَّ الساعة المُدوَّر — إعلانان لوقتٍ واحد لا يتطابقان.
        # والحقيقةُ مزدوجة: حقولُ `current` عند طابعها، والحقولُ الساعيّةُ فقط (ET0/VPD/
        # التربة) من صفّ الساعة. فيُعلَن كلاهما باسمه بدل أن يُخفي أحدُهما الآخر.
        hourly_row_time = resolution["resolved"]
        limitations = list(resolution["limitations"])
        if hourly_row_time is not None and hourly_row_time != c["time"]:
            limitations.append(f"hourly_only_fields_from:{hourly_row_time}")
        resolution = {
            **resolution,
            "anchor": c["time"],
            "target": c["time"],
            "resolved": c["time"],
            "hourly_row_time": hourly_row_time,
            "policy": "current",
            "delta_hours": 0.0,
            "limitations": limitations,
        }
    hourly_index = resolution["index"]

    def hv(key: str):
        return _hourly_value_at(h, key, hourly_index)

    def nvl(*values):
        for value in values:
            if value is not None:
                return value
        return None

    openmeteo_wind_direction = nvl(
        c.get("wind_direction_10m") if use_current else None, hv("wind_direction_10m")
    )

    sample = {
        "lat": lat,
        "lon": lon,
        "requested_time": time_key or "now",
        "model": model or "best_match",
        "time": (c.get("time") if use_current else None) or resolution["resolved"],
        "time_resolution": resolution,
        "temperature_2m_c": (c.get("temperature_2m") if use_current else None)
        or hv("temperature_2m"),
        "relative_humidity_2m_pct": (c.get("relative_humidity_2m") if use_current else None)
        or hv("relative_humidity_2m"),
        "precipitation_mm": (c.get("precipitation") if use_current else None)
        or hv("precipitation"),
        "precipitation_probability_pct": hv("precipitation_probability"),
        "cloud_cover_pct": (c.get("cloud_cover") if use_current else None) or hv("cloud_cover"),
        "pressure_msl_hpa": (c.get("pressure_msl") if use_current else None) or hv("pressure_msl"),
        "surface_pressure_hpa": (c.get("surface_pressure") if use_current else None)
        or hv("surface_pressure"),
        "wind_speed_10m_kmh": (c.get("wind_speed_10m") if use_current else None)
        or hv("wind_speed_10m"),
        "wind_direction_10m_deg": openmeteo_wind_direction,
        "wind_gusts_10m_kmh": (c.get("wind_gusts_10m") if use_current else None)
        or hv("wind_gusts_10m"),
        "weather_code": (c.get("weather_code") if use_current else None) or hv("weather_code"),
        "is_day": c.get("is_day") if use_current else None,
        "vapour_pressure_deficit_kpa": hv("vapour_pressure_deficit"),
        "et0_fao_evapotranspiration_mm": hv("et0_fao_evapotranspiration"),
        "soil_temperature_0cm_c": hv("soil_temperature_0cm"),
        "soil_temperature_6cm_c": hv("soil_temperature_6cm"),
        "soil_temperature_18cm_c": hv("soil_temperature_18cm"),
        "soil_temperature_54cm_c": hv("soil_temperature_54cm"),
        "soil_temperature_10_40cm_c": _soil_temperature_10_40cm(
            hv("soil_temperature_6cm"), hv("soil_temperature_18cm"), hv("soil_temperature_54cm")
        ),
        "soil_moisture_0_to_1cm_m3m3": hv("soil_moisture_0_to_1cm"),
        "soil_moisture_1_to_3cm_m3m3": hv("soil_moisture_1_to_3cm"),
        "soil_moisture_3_to_9cm_m3m3": hv("soil_moisture_3_to_9cm"),
        "source": "open-meteo",
        "wind_direction_source": "open-meteo" if openmeteo_wind_direction is not None else None,
    }

    # احتياط اتّجاه الرياح: حين يغيب من Open-Meteo، نجلبه من MET Norway (مفتوح المصدر،
    # عالميّ) بدل أيّ قيمة وهميّة. صادق: إن تعذّر يبقى None والواجهة لا ترسم أسهماً.
    if sample.get("wind_direction_10m_deg") is None:
        try:
            from api.connectors import metno_wind

            deg = await metno_wind.fetch_wind_direction_deg(lat, lon)
            if deg is not None:
                sample["wind_direction_10m_deg"] = deg
                sample["wind_direction_source"] = "met.no"
        except Exception:  # noqa: BLE001 — الاحتياط لا يكسر العيّنة أبداً
            pass

    return sample


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
