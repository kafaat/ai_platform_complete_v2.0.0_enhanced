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

# عناوين الخدمات الداخليّة (قابلة للضبط من البيئة — افتراضات compose)
WEATHER_URL = os.getenv("WEATHER_SERVICE_URL", "http://sahool-weather-service:8000")
SOIL_URL = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000")
RASTER_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001")
HTTP_TIMEOUT = float(os.getenv("ADAPTER_TIMEOUT", "20.0"))


def _get_json(url: str, params: dict | None = None) -> dict | None:
    """نداء GET آمن — يُرجِع JSON أو None عند أيّ فشل (صدق: لا اختراع)."""
    try:
        import httpx
    except ImportError:
        return None  # بيئة بلا httpx — يُعلَن كمتعذّر
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(url, params=params or {})
            resp.raise_for_status()
            return resp.json()
    except Exception:  # noqa: BLE001 — أيّ فشل → متعذّر (لا نُسقط الطلب)
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
    for k in ("ndvi", "ndre", "ndsi", "ndwi", "bsi", "si"):
        if data.get(k) is not None:
            out[k] = data[k]
    out["resolution_m"] = data.get("resolution_m", 10.0)
    out["field_coverage"] = data.get("field_coverage")
    out["observed_at"] = data.get("observed_at")
    # غطاء السحب — يُمرَّر ليُفعّل تحويل الوزن للرادار في fuse_health (كان مفقوداً)
    if data.get("cloud_cover") is not None:
        out["cloud_cover"] = data["cloud_cover"]
    return out or None


def build_live_adapters() -> dict:
    """يُرجِع قاموس المحوّلات الحيّة لتمريرها لـrun_field_intelligence.

    الاستخدام في endpoint:
        adapters = build_live_adapters()
        run_field_intelligence(req, **adapters, ...)
    """
    return {"weather_fn": weather_adapter, "soil_fn": soil_adapter, "sensing_fn": sensing_adapter}
