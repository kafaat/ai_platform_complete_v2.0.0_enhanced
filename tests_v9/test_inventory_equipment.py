"""Inventory + Equipment layers (CI-enforced) — coverage audit layers 10/11.

كانتا غائبتين 100%. هذه الاختبارات تُثبِت: ① مصفوفة الصلاحيات الجديدة
(inventory/equipment view|manage) صحيحة؛ ② الفرض عبر HTTP — الإدارة محظورة على
الأدوار الدنيا (403)، والعرض مسموح (يمرّ التبويب فيصل لطبقة القاعدة).
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
            "sub": "u_inv",
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
def test_inventory_equipment_permission_matrix(app_mod):
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema

    def u(role):
        return UserSchema(user_id="u", tenant_id="t", role=role, name_ar="x")

    # الإدارة: المالك والمدير فقط
    for role in (UserRole.OWNER, UserRole.MANAGER):
        assert has_permission(u(role), Permission.INVENTORY_MANAGE) is True
        assert has_permission(u(role), Permission.EQUIPMENT_MANAGE) is True
    # الاختصاصي/العامل/المشاهد: عرض فقط، لا إدارة
    for role in (UserRole.AGRONOMIST, UserRole.WORKER, UserRole.VIEWER):
        assert has_permission(u(role), Permission.INVENTORY_VIEW) is True
        assert has_permission(u(role), Permission.EQUIPMENT_VIEW) is True
        assert has_permission(u(role), Permission.INVENTORY_MANAGE) is False
        assert has_permission(u(role), Permission.EQUIPMENT_MANAGE) is False


@pytest.mark.integration
def test_manage_denied_for_low_roles(app_mod):
    """العرض/الإدارة: الأدوار الدنيا تُرفَض (403) على نقاط الإدارة."""
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    # viewer لا يملك inventory:manage ⇒ 403
    r = client.post(
        "/api/v1/inventory/items",
        json={"category": "fertilizer", "name": "يوريا"},
        headers={"Authorization": f"Bearer {_raw_token(m, 'viewer', tenant)}"},
    )
    assert r.status_code == 403, r.text
    # worker لا يملك equipment:manage ⇒ 403
    r = client.post(
        "/api/v1/equipment",
        json={"name": "جرّار ١", "type": "tractor"},
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code == 403, r.text


@pytest.mark.integration
def test_view_allowed_passes_rbac(app_mod):
    """العرض مسموح لكلّ الأدوار ⇒ يتجاوز التبويب (لا 403). بلا قاعدة يصل 503
    (get_pool) — المهمّ أنّ RBAC لم يحجب."""
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    for role in ("viewer", "worker", "agronomist"):
        r = client.get(
            "/api/v1/inventory/items",
            headers={"Authorization": f"Bearer {_raw_token(m, role, tenant)}"},
        )
        assert r.status_code != 403, f"{role}: {r.status_code}"
        r = client.get(
            "/api/v1/equipment",
            headers={"Authorization": f"Bearer {_raw_token(m, role, tenant)}"},
        )
        assert r.status_code != 403, f"{role}: {r.status_code}"


@pytest.mark.integration
def test_bad_date_returns_400_not_500(app_mod):
    """تاريخ غير صالح يُرفَض بـ400 (تحقّق API) قبل لمس القاعدة — لا 500."""
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    # owner يملك equipment:manage ⇒ يتجاوز التبويب؛ التاريخ السيّئ يُرفَض 400
    r = client.post(
        "/api/v1/equipment",
        json={"name": "جرّار", "type": "tractor", "purchase_date": "not-a-date"},
        headers={"Authorization": f"Bearer {_raw_token(m, 'owner', tenant)}"},
    )
    assert r.status_code == 400, r.text
    assert "purchase_date" in r.text
