"""اختبار توصيل نقاط إغلاق دورة الإشعار + تسجيل الحدث.

مسار الكتابة/القراءة تكامليّ (يتطلّب Postgres) — هنا نؤكّد التوصيل (نقطة التسليم +
WebSocket) وتسجيل نوع الحدث NOTIFICATION_DELIVERED فقط (بلا قاعدة).
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّهات
import pytest
from api.event_bus import EventType
from api.event_catalog import get_event, is_registered

pytestmark = pytest.mark.unit


def test_notification_delivered_event_registered():
    """نوع الحدث NOTIFICATION_DELIVERED مُسجَّل في EventType + event_catalog."""
    assert EventType.NOTIFICATION_DELIVERED.value == "notification.delivered"
    assert EventType["NOTIFICATION_DELIVERED"] is EventType.NOTIFICATION_DELIVERED
    assert is_registered("NOTIFICATION_DELIVERED")
    ev = get_event("NOTIFICATION_DELIVERED")
    assert ev is not None and ev["category"] == "notification"
    assert "status" in ev["payload_keys"]


def test_delivery_endpoint_wired():
    """نقطة إيصال التسليم POST مُضمَّنة في الموجِّه القائم."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/notifications/delivery", "POST") in routes
    # نقاط التفضيلات القائمة لم تتأثّر.
    assert ("/api/v1/notifications/preferences", "GET") in routes
    assert ("/api/v1/notifications/preferences", "PUT") in routes


def test_ws_endpoint_wired():
    """نقطة البثّ الحيّ WebSocket مُضمَّنة على الموجِّه القائم (مسار بلا أفعال HTTP)."""
    ws_paths = {r.path for r in api.main.app.routes if r.__class__.__name__ == "APIWebSocketRoute"}
    assert "/api/v1/notifications/ws" in ws_paths


def test_delivery_endpoint_requires_auth():
    """نقطة التسليم مُغيِّرة (POST) ⇒ يجب أن تتطلّب مصادقة (fail-closed، حارس H1)."""

    def _auth_in_tree(dep) -> bool:
        call = getattr(dep, "call", None)
        if call is not None and getattr(call, "__name__", "") in {
            "get_current_user",
            "_require_service_token",
        }:
            return True
        return any(_auth_in_tree(sub) for sub in getattr(dep, "dependencies", []))

    for route in api.main.app.routes:
        if getattr(route, "path", "") == "/api/v1/notifications/delivery":
            if "POST" in getattr(route, "methods", set()):
                assert _auth_in_tree(route.dependant), "نقطة التسليم بلا مصادقة"
                return
    raise AssertionError("نقطة /api/v1/notifications/delivery غير موجودة")
