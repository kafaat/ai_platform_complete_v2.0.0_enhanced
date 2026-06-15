"""Document Management metadata registry (CI-enforced) — سجلّ وصفيّ، لا blob."""

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
            "sub": "u_doc",
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
def test_document_permission_matrix(app_mod):
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema

    def u(role):
        return UserSchema(user_id="u", tenant_id="t", role=role, name_ar="x")

    for role in (UserRole.OWNER, UserRole.MANAGER, UserRole.AGRONOMIST):
        assert has_permission(u(role), Permission.DOCUMENT_MANAGE) is True
        assert has_permission(u(role), Permission.DOCUMENT_VIEW) is True
    for role in (UserRole.WORKER, UserRole.VIEWER):
        assert has_permission(u(role), Permission.DOCUMENT_VIEW) is True
        assert has_permission(u(role), Permission.DOCUMENT_MANAGE) is False


@pytest.mark.integration
def test_manage_denied_view_allowed(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.post(
        "/api/v1/documents",
        json={"category": "contract", "title": "عقد إيجار أرض"},
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code == 403, r.text
    r = client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code in (200, 503), r.text


@pytest.mark.integration
def test_bad_category_422(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.post(
        "/api/v1/documents",
        json={"category": "spreadsheet", "title": "ملفّ"},
        headers={"Authorization": f"Bearer {_raw_token(m, 'agronomist', tenant)}"},
    )
    assert r.status_code == 422, r.text


@pytest.mark.integration
def test_get_single_document_view_allowed(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    r = client.get(
        "/api/v1/documents/doc_nonexistent",
        headers={"Authorization": f"Bearer {_raw_token(m, 'viewer', tenant)}"},
    )
    assert r.status_code in (200, 404, 503), r.text
