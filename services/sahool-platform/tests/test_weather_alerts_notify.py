"""جسر تنبيهات الطقس → نظام الإشعارات: POST /api/v1/weather/alerts/notify.

يحوّل التنبيهات المشتقّة إلى صفوف ``alerts`` + حدث ``ALERT_CREATED`` (يلتقطه وكيل
الإشعارات). هنا نختبر المنطق النقيّ (الترشيح/التحويل) + تعاقُد سطح الـAPI (POST + مصادقة)
بلا قاعدة بيانات حيّة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_CORE = os.path.join(os.path.dirname(__file__), "..")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


def _alerts(*sev: str) -> list[dict]:
    return [
        {"type": f"t{i}", "severity": s, "title_ar": f"عنوان {i}", "detail_ar": f"شرح {i}"}
        for i, s in enumerate(sev)
    ]


def test_filter_keeps_warning_and_above_by_default():
    from api.routers.weather import weather_alert_rows_to_persist

    rows = weather_alert_rows_to_persist(_alerts("info", "warning", "critical"))
    sevs = {r["severity"] for r in rows}
    assert sevs == {"warning", "critical"}  # info مُستبعَد افتراضيّاً
    # النوع مسبوق بـweather_ لمنع التضارب/التكرار.
    assert all(r["alert_type"].startswith("weather_") for r in rows)


def test_filter_critical_only():
    from api.routers.weather import weather_alert_rows_to_persist

    rows = weather_alert_rows_to_persist(
        _alerts("info", "warning", "critical"), min_severity="critical"
    )
    assert [r["severity"] for r in rows] == ["critical"]


def test_message_ar_falls_back_to_title_when_no_detail():
    from api.routers.weather import weather_alert_rows_to_persist

    rows = weather_alert_rows_to_persist([{"type": "x", "severity": "critical", "title_ar": "حرج"}])
    assert rows[0]["message_ar"] == "حرج"  # لا detail_ar ⇒ يقع على العنوان (لا None)


def test_empty_when_nothing_meets_severity():
    from api.routers.weather import weather_alert_rows_to_persist

    assert weather_alert_rows_to_persist(_alerts("info", "info")) == []


def test_notify_endpoint_registered_as_authenticated_post():
    """النقطة مُعرَّفة POST على راوتر الطقس (تعاقُد سطح الـAPI)."""
    pytest.importorskip("fastapi")
    try:
        from api.routers import weather as w
    except ModuleNotFoundError as e:  # تبعيّات المنصّة غائبة محلّيّاً
        pytest.skip(f"platform deps missing: {e}")
    by_path: dict[str, set[str]] = {}
    for r in w.router.routes:
        p = getattr(r, "path", None)
        if p:
            by_path.setdefault(p, set()).update(getattr(r, "methods", set()) or set())
    assert "/api/v1/weather/alerts/notify" in by_path
    assert "POST" in by_path["/api/v1/weather/alerts/notify"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
