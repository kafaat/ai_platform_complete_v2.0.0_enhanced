"""RASTER-COMPAT-PASSTHROUGH-01 — تمرير ``/api/raster/{path}`` لا يصير نائباً مُعتمَداً.

``raster_get_raw`` يرفق توكن خدمة المنصّة، وraster-service صار يُصدّق المستأجِر الذي يُدَّعى
بجانب ذلك التوكن (RASTER-TENANT-TRUST-01). والتمريرُ كان **بلا مصادقة** يُرقّي ``?tid=`` أو
``X-Tenant-Id`` من الطلب إلى ادّعاءٍ موقَّعٍ بتوكن المنصّة — فأيُّ مُنادٍ يبلغ المنصّة يقرأ صور
مستأجِرٍ آخر عبرها حتّى بعد إنفاذ الراستر. المستأجِر هنا مستأجِرُ الـJWT وحدَه.
"""

from __future__ import annotations

from api.main import app  # أوّلاً: main يسجّل الراوترات (compat لا يستورد main على مستواه)
from api.routers import compat_gateway as compat
from core.canonical_schemas import UserRole, UserSchema
from fastapi.testclient import TestClient

OWN = "00000000-0000-0000-0000-00000000000a"
VICTIM = "00000000-0000-0000-0000-00000000000b"


def _capture(monkeypatch):
    calls: list[dict] = []

    async def fake_raw(path, *, tenant_id=None, authorization=None, params=None, timeout_s=30.0):
        calls.append({"path": path, "tenant_id": tenant_id, "params": dict(params or {})})
        return b"{}", 200, "application/json", {}

    monkeypatch.setattr(compat, "raster_get_raw", fake_raw)
    return calls


def test_unauthenticated_caller_is_refused_before_raster_is_called(monkeypatch):
    calls = _capture(monkeypatch)
    client = TestClient(app)
    for headers, query in (
        ({"X-Tenant-Id": VICTIM}, ""),
        ({}, f"&tid={VICTIM}"),
        ({}, f"&tenant_id={VICTIM}"),
    ):
        resp = client.get(f"/api/raster/v1/fields/F/tilejson?index=ndvi{query}", headers=headers)
        assert resp.status_code == 401, (headers, query, resp.status_code)
    assert calls == [], "no credentialed raster call may be made for an unauthenticated caller"


def test_authenticated_caller_asserts_its_own_tenant_not_the_requested_one(monkeypatch):
    calls = _capture(monkeypatch)
    app.dependency_overrides[compat.get_current_user] = lambda: UserSchema(
        user_id="u-own", tenant_id=OWN, role=UserRole.MANAGER, name_ar="مستخدم"
    )
    try:
        resp = TestClient(app).get(
            f"/api/raster/v1/fields/F/tilejson?index=ndvi&tid={VICTIM}&tenant_id={VICTIM}",
            headers={"X-Tenant-Id": VICTIM, "Authorization": "Bearer x"},
        )
    finally:
        app.dependency_overrides.pop(compat.get_current_user, None)
    assert resp.status_code == 200
    assert calls[-1]["tenant_id"] == OWN
    assert "tid" not in calls[-1]["params"] and "tenant_id" not in calls[-1]["params"]
    assert calls[-1]["params"]["index"] == "ndvi"
