"""
field_intelligence_adapters.py — محوّلات المصادر الحيّة (HTTP).

تستبدل نقاط الحقن (mock) في field_intelligence_coordinator بنداءات HTTP
فعليّة للخدمات (weather/soil/raster). تُستدعى من endpoint التشغيل.

التصميم: كلّ محوّل دالّة تأخذ FieldRequest وتُرجِع dict خام أو None (متعذّر).
صدق: عند فشل/تعذّر الخدمة، تُرجِع None (يُعلَن كمصدر متعذّر) — لا تخترع بيانات.
المهلات وإعادة المحاولة محكومة؛ الأخطاء تُلتقَط ولا تُسقط الطلب كلّه.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

# عناوين الخدمات الداخليّة (قابلة للضبط من البيئة — افتراضات compose)
WEATHER_URL = os.getenv("WEATHER_SERVICE_URL", "http://sahool-weather-service:8000")
SOIL_URL = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000")
RASTER_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001")
PLATFORM_URL = os.getenv("PLATFORM_SERVICE_URL", "http://sahool-platform:8000")
HTTP_TIMEOUT = float(os.getenv("ADAPTER_TIMEOUT", "20.0"))

# Open-Meteo — توقّع مجّاني بلا مفتاح API (المصدر الافتراضي للتوقّع الجوّي).
# يُحاوَل دائماً متى توفّرت lat/lon (بلا راية تفعيل — keyless). الانسحاب للنشر
# المعزول: WEATHER_LIVE_DISABLED صادقة ⇒ None. أيّ فشل شبكيّ ⇒ None (صدق، لا اختراع).
OPENMETEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _is_truthy(val: str | None) -> bool:
    """هل قيمة بيئة تعني التفعيل؟ (1/true/yes/on — بلا حساسيّة لحالة الأحرف)."""
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def _auth_headers(authorization: str | None) -> dict | None:
    """رأس التفويض (Bearer) لتمريره للنقاط المحميّة بـJWT. None ⇒ بلا رأس."""
    return {"Authorization": authorization} if authorization else None


def _get_json(
    url: str, params: dict | None = None, *, authorization: str | None = None
) -> dict | None:
    """نداء GET آمن — يُرجِع JSON أو None عند أيّ فشل (صدق: لا اختراع).

    يمرّر رأس التفويض إن وُجد (النقاط المحميّة بـJWT تُرجع 401 بدونه ⇒ None دائماً).
    """
    try:
        import httpx
    except ImportError:
        return None  # بيئة بلا httpx — يُعلَن كمتعذّر
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(url, params=params or {}, headers=_auth_headers(authorization))
            resp.raise_for_status()
            return resp.json()
    except Exception:  # noqa: BLE001 — أيّ فشل → متعذّر (لا نُسقط الطلب)
        return None


def _post_json(
    url: str, payload: dict | None = None, *, authorization: str | None = None
) -> dict | None:
    """نداء POST آمن — يُرجِع JSON أو None عند أيّ فشل (صدق: لا اختراع)."""
    try:
        import httpx
    except ImportError:
        return None
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.post(url, json=payload or {}, headers=_auth_headers(authorization))
            resp.raise_for_status()
            return resp.json()
    except Exception:  # noqa: BLE001 — أيّ فشل → متعذّر
        return None


def weather_adapter(req) -> dict | None:
    """يجلب الطقس الحيّ → {heat_risk, forecast_at}. None عند التعذّر."""
    if req.lat is None or req.lon is None:
        return None
    data = _get_json(f"{WEATHER_URL}/api/v1/weather", {"lat": req.lat, "lon": req.lon})
    if not data:
        return None
    # تطبيع لمخطّط المنسّق (heat_risk من مؤشّر الإجهاد الحراري)
    return {
        "heat_risk": data.get("heat_stress_index", data.get("heat_risk")),
        "forecast_at": data.get("forecast_at"),
    }


def weather_forecast_adapter(req, *, authorization: str | None = None) -> dict | None:
    """يجلب توقّع الطقس الحيّ (7 أيّام) من Open-Meteo → مخطّط مطبَّع. None عند التعذّر.

    Open-Meteo مجّاني بلا مفتاح ⇒ هو المصدر الافتراضي: يُحاوَل النداء دائماً متى
    توفّرت lat/lon (بلا راية تفعيل). الانسحاب (air-gapped): WEATHER_LIVE_DISABLED.
    الصدق: عند أيّ فشل (منع الخروج/≠200/تفكيك/غياب httpx) → None — لا أرقام مخترَعة.
    """
    if _is_truthy(os.getenv("WEATHER_LIVE_DISABLED")):
        return None  # انسحاب صريح للنشر المعزول
    if req.lat is None or req.lon is None:
        return None
    try:
        import httpx
    except ImportError:
        return None  # بيئة بلا httpx — يُعلَن كمتعذّر
    params = {
        "latitude": req.lat,
        "longitude": req.lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
        "et0_fao_evapotranspiration,wind_speed_10m_max,weather_code",
        "timezone": "auto",
        "wind_speed_unit": "ms",
        "forecast_days": 7,
    }
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(OPENMETEO_FORECAST_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001 — أيّ فشل → متعذّر (لا نُسقط الطلب)
        return None
    daily = data.get("daily") if isinstance(data, dict) else None
    if not isinstance(daily, dict):
        return None
    dates = daily.get("time")
    if not isinstance(dates, list) or not dates:
        return None

    def _at(key: str, i: int):
        lst = daily.get(key)
        if not isinstance(lst, list) or i >= len(lst):
            return None
        return lst[i]

    days = [
        {
            "date": date,
            "temp_max_c": _at("temperature_2m_max", i),
            "temp_min_c": _at("temperature_2m_min", i),
            "precipitation_mm": _at("precipitation_sum", i),
            "et0_mm": _at("et0_fao_evapotranspiration", i),
            "wind_max_ms": _at("wind_speed_10m_max", i),
            "weather_code": _at("weather_code", i),
        }
        for i, date in enumerate(dates)
    ]
    if not days:
        return None
    return {
        "source": "open-meteo",
        "forecast_at": dates[0],
        "fetched_at": datetime.now(UTC).isoformat(),
        "elevation_m": data.get("elevation"),
        "daily": days,
    }


def soil_adapter(req) -> dict | None:
    """يجلب تحليل التربة → {ec_dsm, sampled_at}. None عند التعذّر."""
    data = _get_json(f"{SOIL_URL}/api/v1/soil/{req.field_id}")
    if not data:
        return None
    return {"ec_dsm": data.get("ec_dsm", data.get("ec")), "sampled_at": data.get("sampled_at")}


def sensing_adapter(req) -> dict | None:
    """يجلب مؤشّرات الاستشعار → {ndvi, ndre, ...}. None عند التعذّر."""
    if req.lat is None or req.lon is None:
        return None
    data = _get_json(
        f"{RASTER_URL}/indices", {"field_id": req.field_id, "lat": req.lat, "lon": req.lon}
    )
    if not data:
        return None
    # تمرير المؤشّرات المتاحة فقط (الغائب يُعلَن في المايسترو)
    out = {}
    for k in ("ndvi", "ndre", "ndsi", "ndwi", "bsi", "si", "rvi"):
        if data.get(k) is not None:
            out[k] = data[k]
    out["resolution_m"] = data.get("resolution_m", 10.0)
    out["field_coverage"] = data.get("field_coverage")
    out["observed_at"] = data.get("observed_at")
    # غطاء السحب — يُمرَّر ليُفعّل تحويل الوزن للرادار في fuse_health (كان مفقوداً)
    if data.get("cloud_cover") is not None:
        out["cloud_cover"] = data["cloud_cover"]
    return out or None


def memory_adapter(req, *, authorization: str | None = None) -> dict | None:
    """يجلب السياق التاريخي للحقل (farm_memory) → {recurring_issues, ...}.

    Runtime Cohesion: يصل ذاكرة الحقل بحلقة القرار. يقرأ تاريخ الأحداث من
    خدمة المنصّة (events عبر event_replay)، يكشف القضايا المتكرّرة (ملوحة/
    إجهاد يتكرّر) لإغناء القرار. None عند التعذّر (صدق: لا تاريخ مخترَع).

    النقطة محميّة بـJWT ⇒ يجب تمرير authorization وإلّا تُرجِع 401 (⇒ None دائماً).
    """
    data = _get_json(
        f"{PLATFORM_URL}/api/v1/fields/{req.field_id}/history",
        {"tenant_id": req.tenant_id},
        authorization=authorization,
    )
    if not data:
        return None
    events = data.get("events", [])
    if not events:
        return {
            "recurring_issues": [],
            "total_events": 0,
            "note_ar": "لا تاريخ مسجّل بعد لهذا الحقل",
        }
    # كشف التكرار: قضايا ظهرت ≥ مرّتين في التاريخ (سياق للقرار)
    issue_counts: dict = {}
    for e in events:
        for tag in e.get("issue_tags") or []:
            issue_counts[tag] = issue_counts.get(tag, 0) + 1
    recurring = [k for k, v in issue_counts.items() if v >= 2]
    return {
        "recurring_issues": recurring,
        "total_events": len(events),
        "issue_counts": issue_counts,
    }


def simulate_adapter(req, decision, state, *, authorization: str | None = None) -> dict | None:
    """يشغّل محاكاة what-if لتقدير أثر الإجراء المقترَح على المحصول/الماء.

    Runtime Cohesion: يصل المحاكاة بحلقة القرار. يطلب من خدمة WOFOST محاكاة
    سيناريو (مثلاً: مع/بلا تدخّل) ويقارن. None عند التعذّر (لا أرقام مخترَعة).
    """
    crop = req.crop or "قمح صلب"
    payload = {
        "field_id": req.field_id,
        "crop": crop,
        "lat": req.lat,
        "lon": req.lon,
        "scenario": "recommended_action",  # الخدمة تفسّر القرار المقترَح
    }
    data = _post_json(
        f"{PLATFORM_URL}/api/v1/simulate/what-if", payload, authorization=authorization
    )
    if not data:
        return None
    # هل الإجراء المقترَح يُحسّن النتيجة فعلاً؟ (للقرار)
    baseline = data.get("baseline_yield_t_ha")
    with_action = data.get("action_yield_t_ha")
    helps = None
    if baseline is not None and with_action is not None:
        helps = with_action > baseline * 1.02  # تحسّن >2% يُعتبر مُجدياً
    return {
        "baseline_yield_t_ha": baseline,
        "action_yield_t_ha": with_action,
        "water_saved_mm": data.get("water_saved_mm"),
        "recommended_action_helps": helps,
    }


def build_live_adapters(authorization: str | None = None) -> dict:
    """يُرجِع قاموس المحوّلات الحيّة لتمريرها لـrun_field_intelligence.

    authorization: رأس التفويض القادم من الطلب. يُمرَّر للمحوّلات المحميّة بـJWT
    (memory/simulate تنادي نقاط المنصّة المحميّة ⇒ بدونه تُرجِع 401 ثمّ None).
    الطقس/التربة/الاستشعار خدمات داخليّة لا تتطلّبه (تبقى كما هي).

    الاستخدام في endpoint:
        adapters = build_live_adapters(authorization=authorization)
        run_field_intelligence(req, **adapters, ...)
    """

    def memory_fn(req):
        return memory_adapter(req, authorization=authorization)

    def simulate_fn(req, decision, state):
        return simulate_adapter(req, decision, state, authorization=authorization)

    return {
        "weather_fn": weather_adapter,
        "soil_fn": soil_adapter,
        "sensing_fn": sensing_adapter,
        "memory_fn": memory_fn,
        "simulate_fn": simulate_fn,
    }
