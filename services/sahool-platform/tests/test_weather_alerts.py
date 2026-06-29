"""اختبارات اشتقاق تنبيهات الطقس (derive_weather_alerts) — منطق نقيّ.

تغطّي: رياح قويّة + تأجيل الرشّ لعيّنة رياح/مطر مرتفعة، صقيع لحرارة تحت الصفر،
موجة حرّ لحرارة عالية جدّاً، وفرصة رشّ ممتازة لجوّ هادئ/جافّ. كما تثبّت تسجيل
نقطة ``/api/v1/weather/alerts`` على راوتر الطقس بطريقة GET (تعاقُد سطح الـAPI).
لا حاجة لقاعدة بيانات أو خدمات خارجيّة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_CORE = os.path.join(os.path.dirname(__file__), "..", "..", "sahool-platform")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from api.weather_alerts import derive_weather_alerts  # noqa: E402


def _types(alerts: list[dict]) -> set[str]:
    return {a["type"] for a in alerts}


def test_strong_wind_and_postpone_spray_for_high_wind_rain():
    sample = {
        "wind_speed_10m_kmh": 32.0,
        "wind_gusts_10m_kmh": 48.0,
        "precipitation_mm": 1.5,
        "temperature_2m_c": 24.0,
        "relative_humidity_2m_pct": 60.0,
    }
    alerts = derive_weather_alerts(sample, None)
    t = _types(alerts)
    assert "strong_wind" in t
    assert "postpone_spray" in t
    assert "excellent_spray_window" not in t
    sw = next(a for a in alerts if a["type"] == "strong_wind")
    assert sw["severity"] in {"warning", "critical"}
    assert sw["title_ar"] == "رياح قويّة"


def test_frost_for_subzero_temps():
    sample = {
        "temperature_2m_c": -3.0,
        "wind_speed_10m_kmh": 4.0,
        "precipitation_mm": 0.0,
        "relative_humidity_2m_pct": 70.0,
    }
    alerts = derive_weather_alerts(sample, None)
    frost = next(a for a in alerts if a["type"] == "frost")
    assert frost["severity"] == "critical"
    assert frost["title_ar"] == "صقيع"
    # حرارة تحت الصفر تمنع الرشّ أيضاً.
    assert "postpone_spray" in _types(alerts)


def test_heat_wave_for_very_hot():
    sample = {
        "temperature_2m_c": 43.0,
        "wind_speed_10m_kmh": 6.0,
        "precipitation_mm": 0.0,
        "relative_humidity_2m_pct": 20.0,
    }
    alerts = derive_weather_alerts(sample, None)
    heat = next(a for a in alerts if a["type"] == "heat_wave")
    assert heat["severity"] == "critical"
    assert heat["title_ar"] == "موجة حرّ"


def test_excellent_spray_window_for_calm_dry():
    sample = {
        "temperature_2m_c": 24.0,
        "wind_speed_10m_kmh": 8.0,
        "wind_gusts_10m_kmh": 12.0,
        "precipitation_mm": 0.0,
        "relative_humidity_2m_pct": 50.0,
    }
    alerts = derive_weather_alerts(sample, None)
    t = _types(alerts)
    assert "excellent_spray_window" in t
    assert "postpone_spray" not in t
    assert "strong_wind" not in t


def test_possible_disease_high_humidity_mild_temp():
    sample = {
        "temperature_2m_c": 22.0,
        "wind_speed_10m_kmh": 5.0,
        "precipitation_mm": 0.0,
        "relative_humidity_2m_pct": 93.0,
    }
    alerts = derive_weather_alerts(sample, None)
    assert "possible_disease" in _types(alerts)


def test_empty_sample_is_safe():
    alerts = derive_weather_alerts({}, None)
    # عيّنة فارغة تُعامل كجوّ هادئ → فرصة رشّ ممتازة بلا انهيار.
    assert "excellent_spray_window" in _types(alerts)


def _load_router():
    pytest.importorskip("fastapi")
    try:
        import api.routers.weather as w
    except ModuleNotFoundError as e:  # تبعيّات المنصّة غائبة محلّيّاً
        pytest.skip(f"platform deps missing: {e}")
    return w


def test_weather_alerts_endpoint_registered_as_get():
    """نقطة /api/v1/weather/alerts مُعرَّفة على راوتر الطقس بطريقة GET."""
    w = _load_router()
    by_path: dict[str, set[str]] = {}
    for r in w.router.routes:
        p = getattr(r, "path", None)
        if p:
            by_path.setdefault(p, set()).update(getattr(r, "methods", set()) or set())
    assert "/api/v1/weather/alerts" in by_path, "نقطة تنبيهات الطقس غير مُعرَّفة"
    assert "GET" in by_path["/api/v1/weather/alerts"], "alerts ليست GET"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
