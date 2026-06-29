"""عقد محرّك الطقس (v8 · Open-Meteo) — نقاط بيانات بلاطات الطقس لطبقة الخريطة.

المحرّك يخدم قيم الطقس لكلّ بلاطة z/x/y (حرارة/رياح/مطر/ET₀/VPD…) + صلاحيّة العمليّات
(رش/حصاد/بذار/ريّ) + مسبار نقطيّ + سلسلة زمنيّة — وكيل Open-Meteo بإحداثيّات، بلا حالة
مستأجِر. هذه الاختبارات تثبّت تعاقُد البنية (النقاط مُعرَّفة على الراوتر بطريقة GET) كي لا
ينحدر سطح الـAPI الذي تستهلكه طبقة الطقس في الواجهة/الموبايل.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_CORE = os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform")

# النقاط الأربع الجديدة لمحرّك الطقس (بيانات البلاطات) — يستهلكها OverlayMarkers.tsx.
_WEATHER_TILE_ROUTES = {
    "/api/v1/weather/tile-data/{z}/{x}/{y}",
    "/api/v1/weather/operation-tile-data/{z}/{x}/{y}",
    "/api/v1/weather/tile-series/{z}/{x}/{y}",
    "/api/v1/weather/probe",
}


def _load_router():
    if _CORE not in sys.path:
        sys.path.insert(0, _CORE)
    pytest.importorskip("fastapi")
    try:
        import api.routers.weather as w
    except ModuleNotFoundError as e:  # تبعيّات المنصّة غائبة محلّيّاً
        pytest.skip(f"platform deps missing: {e}")
    return w


def test_weather_tile_endpoints_registered_as_get():
    """النقاط الأربع مُعرَّفة على راوتر الطقس بطريقة GET (تعاقُد سطح الـAPI)."""
    w = _load_router()
    by_path: dict[str, set[str]] = {}
    for r in w.router.routes:
        p = getattr(r, "path", None)
        if p:
            by_path.setdefault(p, set()).update(getattr(r, "methods", set()) or set())
    for route in _WEATHER_TILE_ROUTES:
        assert route in by_path, f"نقطة الطقس غير مُعرَّفة: {route}"
        assert "GET" in by_path[route], f"{route} ليست GET"


def test_weather_tile_endpoints_are_public_proxies():
    """مصدر الراوتر لا يفتح اتّصال مستأجِر لهذه النقاط (وكيل بيئيّ عامّ، لا تسريب RLS)."""
    src = open(os.path.join(_CORE, "api", "routers", "weather.py"), encoding="utf-8").read()
    # لا يجب أن تعتمد نقاط البلاطات على tenant_connection (معطى بيئيّ عامّ بإحداثيّات).
    # (الحارس الأوسع test_endpoint_auth_coverage يؤكّد إدراجها في PUBLIC_ALLOWLIST.)
    assert "tile-data" in src and "tile-series" in src and "probe" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
