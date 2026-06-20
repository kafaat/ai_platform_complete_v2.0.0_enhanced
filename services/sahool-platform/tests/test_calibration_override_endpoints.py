"""اختبار توصيل نقاط المعايرة المُدارة DB-backed (البند 3) + تسجيل الحدث.

مسار الكتابة/القراءة تكامليّ (يتطلّب Postgres) — هنا نؤكّد التوصيل وتسجيل نوع الحدث فقط.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّهات
import pytest
from api.event_bus import EventType
from api.event_catalog import get_event, is_registered

pytestmark = pytest.mark.unit


def test_calibration_override_event_registered():
    """نوع الحدث CALIBRATION_OVERRIDE_SET مُسجَّل في EventType + event_catalog."""
    assert EventType.CALIBRATION_OVERRIDE_SET.value == "calibration.override.set"
    assert EventType["CALIBRATION_OVERRIDE_SET"] is EventType.CALIBRATION_OVERRIDE_SET
    assert is_registered("CALIBRATION_OVERRIDE_SET")
    ev = get_event("CALIBRATION_OVERRIDE_SET")
    assert ev is not None and ev["category"] == "calibration"


def test_managed_override_endpoints_wired():
    """نقاط المعايرة المُدارة الأربع مُضمَّنة بأفعالها الصحيحة (POST/GET/GET/DELETE)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/calibration/{region}/override", "POST") in routes
    assert ("/api/v1/calibration/{region}/override", "DELETE") in routes
    assert ("/api/v1/calibration/{region}/resolved", "GET") in routes
    assert ("/api/v1/calibration/overrides/all", "GET") in routes


def test_overrides_list_path_not_shadowed_by_region():
    """مسار القائمة (2-segment) لا يُحجَب بـ/calibration/{region} (1-segment) — تحقّق توجيه."""
    paths = {r.path for r in api.main.app.routes}
    assert "/api/v1/calibration/overrides/all" in paths
    assert "/api/v1/calibration/{region}" in paths  # القائمة أطول مساراً ⇒ لا تعارض
