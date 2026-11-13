"""``POST /api/v1/work-orders/from-recommendation`` يتطلّب ``ACTIVITY_PLAN``.

الفجوة (تمرين المشرف ← المفتّش، ٢٠٢٦-١١-١٢): كان المسار بـ``get_current_user`` وحده،
فكان المشاهِد والعامل يُنشئان أوامر عملٍ مُثبَّتة. الرفضُ يقع في التبعيّة قبل أيّ اتّصال
بقاعدة، فيُقاس عبر HTTP بلا قاعدة: على main كان الطلبُ يصل المعالِج ويُعيد 200.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "services" / "sahool-platform"
TENANT = "11111111-1111-1111-1111-111111111111"
PATH = "/api/v1/work-orders/from-recommendation"
BODY = {
    "field_id": "fld-1",
    "recommendation": {"action_type": "irrigate", "recommendation_id": "rec-1"},
}


@pytest.fixture(scope="module")
def app_mod():
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    pytest.importorskip("fastapi")
    import api.main as m

    return m


def _token(m, role: str) -> str:
    now = datetime.now(UTC)
    return m.jwt.encode(
        {
            "sub": "u_wo_rbac",
            "tenant_id": TENANT,
            "role": role,
            "name_ar": "مختبِر",
            "aud": "sahool",
            "iss": "sahool-platform",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        m.JWT_SECRET,
        algorithm=m.JWT_ALGORITHM,
    )


# farmer ⇒ WORKER عبر _ROLE_ALIASES: مستخدمو خدمة الهويّة «farmer» يُرفَضون كذلك.
@pytest.mark.parametrize("role", ["viewer", "worker", "farmer"])
def test_viewer_and_worker_cannot_create_work_orders(app_mod, role):
    from fastapi.testclient import TestClient

    client = TestClient(app_mod.app, raise_server_exceptions=False)
    r = client.post(PATH, json=BODY, headers={"Authorization": f"Bearer {_token(app_mod, role)}"})
    assert r.status_code == 403, r.text
    assert "activity:plan" in r.text


@pytest.mark.parametrize("role", ["owner", "manager", "agronomist"])
def test_planners_pass_the_permission_dependency(app_mod, role):
    from api.routers import agro_intelligence
    from core.canonical_schemas import UserRole, UserSchema

    route = next(r for r in agro_intelligence.router.routes if getattr(r, "path", None) == PATH)
    dep = next(d.call for d in route.dependant.dependencies if d.name == "user")
    user = UserSchema(user_id="u1", tenant_id=TENANT, role=UserRole(role), name_ar="مخطِّط")
    assert dep(user=user) is user


def test_pure_agro_compute_routes_keep_authenticated_only_access(app_mod):
    """النقاطُ الحسابيّة الصرفة (بلا كتابة) لم تُشدَّد: الصلاحيةُ على مسار الكتابة وحده."""
    from api.main import get_current_user
    from api.routers import agro_intelligence

    for route in agro_intelligence.router.routes:
        dep = next(d.call for d in route.dependant.dependencies if d.name == "user")
        if route.path == PATH:
            assert dep is not get_current_user
        else:
            assert route.path.startswith("/api/v1/agro/") and dep is get_current_user
