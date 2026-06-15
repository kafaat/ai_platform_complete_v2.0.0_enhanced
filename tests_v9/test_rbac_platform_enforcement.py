"""RBAC enforcement at the platform HTTP layer (CI-enforced).

الفجوة المعياريّة المسدودة: محرّك الصلاحيات (core.authorization) كان مفروضاً
في خطّ التوصيات فقط، لا عند نقاط HTTP — أيّ مستخدم مُصادَق كان يفعل أيّ شيء داخل
مستأجره. هذه الاختبارات تُثبِت أنّ `require_permission` يفرض الدور فعليّاً عبر
HTTP (TestClient)، وأنّ تطبيع الأدوار عبر حدود الخدمات (admin/expert/farmer →
النموذج الخماسي) يعمل ولا يهبط 'admin' صامتاً إلى أدنى صلاحية.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def app_mod():
    # ملاحظة: لا نضبط سرّاً عبر البيئة. main.py يقرأ SAHOOL_JWT_SECRET عند الاستيراد
    # (افتراضه dev-secret في الاختبار)، و_raw_token يوقّع بـm.JWT_SECRET نفسه الذي
    # حمّله التطبيق — فالتوكنات تُقبَل أيّاً كان السرّ المُحمَّل (لا اعتماد على قوّته).
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m

    return m


def _raw_token(m, role: str | None, tenant: str, user_id: str = "u_rbac") -> str:
    """توكن بادّعاء دور خام (يحاكي خدمة auth: admin/expert/farmer)."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "tenant_id": tenant,
        "name_ar": "مختبر",
        "aud": "sahool",
        "iss": "sahool-platform",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    if role is not None:
        payload["role"] = role
    return m.jwt.encode(payload, m.JWT_SECRET, algorithm=m.JWT_ALGORITHM)


def _obs_body(tenant: str) -> dict:
    return {
        "tenant_id": tenant,
        "observable_id": "obs_ndvi",
        "value": 0.62,
        "measured_at": "2026-06-11T08:00:00Z",
    }


def _rec_body(tenant: str) -> dict:
    return {
        "tenant_id": tenant,
        "farm_id": "frm_001",
        "field_id": "fld_001",
        "crop": "قمح صلب",
        "validation": {},
    }


# ─── تطبيع الأدوار (دالّة نقيّة — حتميّة) ───────────────────────────


@pytest.mark.unit
def test_role_normalization_bridges_auth_to_core(app_mod):
    m = app_mod
    from core.canonical_schemas import UserRole

    cases = {
        "owner": UserRole.OWNER,
        "admin": UserRole.OWNER,  # خدمة auth → owner (لا هبوط صامت)
        "manager": UserRole.MANAGER,
        "agronomist": UserRole.AGRONOMIST,
        "expert": UserRole.AGRONOMIST,  # auth → agronomist
        "worker": UserRole.WORKER,
        "farmer": UserRole.WORKER,  # auth → worker
        "viewer": UserRole.VIEWER,
        "ADMIN": UserRole.OWNER,  # غير حسّاس لحالة الأحرف
        "  expert ": UserRole.AGRONOMIST,  # يُشذَّب
    }
    for raw, expected in cases.items():
        assert m._normalize_role(raw) == expected, raw
    # fail-closed: المجهول/الناقص ⇒ أقلّ صلاحية
    assert m._normalize_role(None) == UserRole.VIEWER
    assert m._normalize_role("") == UserRole.VIEWER
    assert m._normalize_role("superadmin") == UserRole.VIEWER


@pytest.mark.unit
def test_permission_matrix_sanity(app_mod):
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema

    def u(role):
        return UserSchema(user_id="u", tenant_id="t", role=role, name_ar="x")

    # عامل يسجّل مشاهدات لكن لا يطلب توصيات
    assert has_permission(u(UserRole.WORKER), Permission.OBSERVATION_RECORD) is True
    assert has_permission(u(UserRole.WORKER), Permission.RECOMMENDATION_REQUEST) is False
    # مشاهد قراءة فقط — لا تسجيل
    assert has_permission(u(UserRole.VIEWER), Permission.OBSERVATION_RECORD) is False
    # مهندس يوافق على المبيدات (تصعيد الآفات)
    assert has_permission(u(UserRole.AGRONOMIST), Permission.PESTICIDE_APPROVE) is True
    # مستخدم غير نشط — يُمنَع كلّ شيء
    inactive = UserSchema(
        user_id="u", tenant_id="t", role=UserRole.OWNER, name_ar="x", is_active=False
    )
    assert has_permission(inactive, Permission.OBSERVATION_RECORD) is False


# ─── الفرض الفعلي عبر HTTP (TestClient) ────────────────────────────


@pytest.mark.integration
def test_viewer_denied_on_observations(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.post(
        "/api/v1/observations",
        json=_obs_body(tenant),
        headers={"Authorization": f"Bearer {_raw_token(m, 'viewer', tenant)}"},
    )
    assert r.status_code == 403, r.text
    assert "viewer" in r.text and "observation:record" in r.text


@pytest.mark.integration
def test_worker_denied_on_recommendations(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.post(
        "/api/v1/recommendations",
        json=_rec_body(tenant),
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code == 403, r.text
    assert "recommendation:request" in r.text


@pytest.mark.integration
def test_worker_allowed_on_observations(app_mod):
    """العامل يملك OBSERVATION_RECORD — يجب ألّا يُرفَض (ليس 403)."""
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.post(
        "/api/v1/observations",
        json=_obs_body(tenant),
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    # نجاح صريح (200 + مسجّل) — لا نكتفي بـ«ليس 403» حتى لا تتسلّل انحدارات 4xx/5xx
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "recorded", r.text


@pytest.mark.integration
def test_admin_alias_normalized_and_allowed(app_mod):
    """توكن خدمة auth بدور 'admin' يُطبَّع إلى owner ⇒ يمرّ على نقطة محميّة
    (لا يهبط صامتاً إلى viewer/worker فيُرفَض زوراً)."""
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.post(
        "/api/v1/recommendations",
        json=_rec_body(tenant),
        headers={"Authorization": f"Bearer {_raw_token(m, 'admin', tenant)}"},
    )
    assert r.status_code != 403, r.text


@pytest.mark.integration
def test_unauthenticated_rejected_on_gated_endpoint(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    client = TestClient(m.app)
    r = client.post("/api/v1/observations", json=_obs_body(str(uuid.uuid4())))
    assert r.status_code == 401, r.text
