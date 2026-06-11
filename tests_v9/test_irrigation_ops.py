"""Irrigation operations (CI-enforced) — coverage audit layer 3.

كان الري إرشاديّاً فقط (حساب FAO-56) دون جداول مُستمرّة ولا نمذجة صمامات. هذه
الاختبارات تُثبِت صلاحيّات الري والفرض عبر HTTP + رفض الوقت غير الصالح بـ400.
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
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m

    return m


def _raw_token(m, role: str, tenant: str) -> str:
    now = datetime.now(UTC)
    return m.jwt.encode(
        {
            "sub": "u_irr",
            "tenant_id": tenant,
            "role": role,
            "name_ar": "مختبر",
            "aud": "sahool",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        m.JWT_SECRET,
        algorithm=m.JWT_ALGORITHM,
    )


@pytest.mark.unit
def test_irrigation_permission_matrix(app_mod):
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema

    def u(role):
        return UserSchema(user_id="u", tenant_id="t", role=role, name_ar="x")

    for role in (UserRole.OWNER, UserRole.MANAGER, UserRole.AGRONOMIST):
        assert has_permission(u(role), Permission.IRRIGATION_MANAGE) is True
    for role in (UserRole.WORKER, UserRole.VIEWER):
        assert has_permission(u(role), Permission.IRRIGATION_VIEW) is True
        assert has_permission(u(role), Permission.IRRIGATION_MANAGE) is False


@pytest.mark.integration
def test_manage_denied_view_allowed(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    # worker لا يملك irrigation:manage ⇒ 403 على إنشاء جدول
    r = client.post(
        "/api/v1/irrigation/schedules",
        json={"name": "ريّ صباحي", "start_time": "06:00", "duration_min": 30},
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code == 403, r.text
    # worker يملك irrigation:view ⇒ يتجاوز التبويب. في بيئة بلا قاعدة يصل 503
    # (get_pool)، ومعها 200 — نستبعد 403 (حجب) و500 (عطل) صراحةً (ملاحظة المراجعة).
    r = client.get(
        "/api/v1/irrigation/valves",
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code in (200, 503), r.text


@pytest.mark.integration
def test_bad_start_time_returns_400(app_mod):
    """وقت بدء غير صالح يُرفَض بـ400 قبل لمس القاعدة (لا 500)."""
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    # agronomist يملك irrigation:manage ⇒ يتجاوز التبويب؛ الوقت السيّئ ⇒ 400
    r = client.post(
        "/api/v1/irrigation/schedules",
        json={"name": "ريّ", "start_time": "25:99", "duration_min": 30},
        headers={"Authorization": f"Bearer {_raw_token(m, 'agronomist', tenant)}"},
    )
    assert r.status_code == 400, r.text
    assert "start_time" in r.text
