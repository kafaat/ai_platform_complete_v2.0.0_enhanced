"""Cost Analytics — تكاليف فعليّة مُجمَّعة (CI-enforced)."""

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
            "sub": "u_ca",
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
def test_cost_analytics_permission_matrix(app_mod):
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema

    def u(role):
        return UserSchema(user_id="u", tenant_id="t", role=role, name_ar="x")

    for role in (UserRole.OWNER, UserRole.MANAGER, UserRole.AGRONOMIST):
        assert has_permission(u(role), Permission.ANALYTICS_VIEW) is True
    for role in (UserRole.WORKER, UserRole.VIEWER):
        assert has_permission(u(role), Permission.ANALYTICS_VIEW) is False


@pytest.mark.integration
def test_worker_denied_agronomist_allowed(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.get(
        "/api/v1/analytics/costs",
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code == 403, r.text
    r = client.get(
        "/api/v1/analytics/costs",
        headers={"Authorization": f"Bearer {_raw_token(m, 'agronomist', tenant)}"},
    )
    assert r.status_code in (200, 503), r.text
