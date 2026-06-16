"""اختبار سلوكيّ: مسارات DLQ المباشرة لِـoutbox مُسجّلة فعلاً وقت التشغيل.

تُحمّل api.main.app (يُحمَّل دون قاعدة بيانات) وتفحص app.routes — تأكيد أنّ نقاط
الفحص/إعادة الجدولة الجديدة (/api/v1/admin/outbox/dead-letter[...]) مُضمَّنة. منطق
الـSELECT/UPDATE نفسه تكامليّ (يحتاج Postgres) ولا يُختبر هنا.
"""

import pytest
from api.main import app

pytestmark = pytest.mark.unit


def _route_paths_methods() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        if isinstance(path, str):
            out.setdefault(path, set()).update(getattr(r, "methods", set()) or set())
    return out


def test_outbox_dead_letter_inspect_route_registered():
    rm = _route_paths_methods()
    assert "/api/v1/admin/outbox/dead-letter" in rm
    assert "GET" in rm["/api/v1/admin/outbox/dead-letter"]


def test_outbox_dead_letter_requeue_route_registered():
    rm = _route_paths_methods()
    assert "/api/v1/admin/outbox/dead-letter/requeue" in rm
    assert "POST" in rm["/api/v1/admin/outbox/dead-letter/requeue"]


def test_openapi_still_builds():
    schema = app.openapi()
    assert "/api/v1/admin/outbox/dead-letter" in schema["paths"]
    assert "/api/v1/admin/outbox/dead-letter/requeue" in schema["paths"]
