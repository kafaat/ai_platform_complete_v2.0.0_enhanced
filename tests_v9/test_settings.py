"""Settings (CI-enforced) — مخزن إعدادات المستأجر الموحّد (v28)."""

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
            "sub": "u_set",
            "tenant_id": tenant,
            "role": role,
            "name_ar": "مختبر",
            "aud": "sahool",
            "iss": "sahool-platform",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        m.JWT_SECRET,
        algorithm=m.JWT_ALGORITHM,
    )


@pytest.mark.unit
def test_settings_permission_matrix(app_mod):
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema

    def u(role):
        return UserSchema(user_id="u", tenant_id="t", role=role, name_ar="x")

    for role in (UserRole.OWNER, UserRole.MANAGER):
        assert has_permission(u(role), Permission.SETTINGS_MANAGE) is True
        assert has_permission(u(role), Permission.SETTINGS_VIEW) is True
    for role in (UserRole.AGRONOMIST, UserRole.WORKER, UserRole.VIEWER):
        assert has_permission(u(role), Permission.SETTINGS_VIEW) is True
        assert has_permission(u(role), Permission.SETTINGS_MANAGE) is False


@pytest.mark.integration
def test_manage_denied_view_allowed(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.put(
        "/api/v1/settings",
        json={"scope": "platform", "key": "locale", "value": {"lang": "ar"}},
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code == 403, r.text
    r = client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code in (200, 503), r.text


@pytest.mark.integration
def test_bad_scope_422(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.put(
        "/api/v1/settings",
        json={"scope": "bogus", "key": "x", "value": {}},
        headers={"Authorization": f"Bearer {_raw_token(m, 'owner', tenant)}"},
    )
    assert r.status_code == 422, r.text
