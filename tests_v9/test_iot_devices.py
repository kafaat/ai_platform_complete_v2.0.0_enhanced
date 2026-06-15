"""IoT device registry + telemetry (CI-enforced) — coverage audit layer 4.

كانت الطبقة 🔴: actuator يُرسل MQTT لكن لا سجلّ أجهزة/صحّة/ابتلاع قراءات. هذه
الاختبارات تُثبِت مصفوفة صلاحيّات الأجهزة والفرض عبر HTTP (الإدارة محظورة على
الأدوار الدنيا؛ ابتلاع القراءة من صلاحية observation:record لا device).
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
            "sub": "u_iot",
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
def test_device_permission_matrix(app_mod):
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema

    def u(role):
        return UserSchema(user_id="u", tenant_id="t", role=role, name_ar="x")

    for role in (UserRole.OWNER, UserRole.MANAGER):
        assert has_permission(u(role), Permission.DEVICE_MANAGE) is True
    for role in (UserRole.AGRONOMIST, UserRole.WORKER, UserRole.VIEWER):
        assert has_permission(u(role), Permission.DEVICE_VIEW) is True
        assert has_permission(u(role), Permission.DEVICE_MANAGE) is False


@pytest.mark.integration
def test_register_denied_for_low_roles(app_mod):
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    for role in ("viewer", "worker", "agronomist"):
        r = client.post(
            "/api/v1/devices",
            json={"name": "حسّاس رطوبة", "type": "soil_moisture"},
            headers={"Authorization": f"Bearer {_raw_token(m, role, tenant)}"},
        )
        assert r.status_code == 403, f"{role}: {r.text}"


@pytest.mark.integration
def test_view_and_telemetry_pass_rbac(app_mod):
    """العرض مسموح لكلّ الأدوار؛ ابتلاع القراءة مسموح لـworker (observation:record)
    لكن محظور على viewer. (بلا قاعدة يصل 503/404 — المهمّ أنّ RBAC لم يحجب بـ403.)"""
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    # العرض: كلّ الأدوار ≠ 403
    for role in ("viewer", "worker"):
        r = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {_raw_token(m, role, tenant)}"},
        )
        assert r.status_code != 403, f"{role}: {r.status_code}"
    body = {"sensor_type": "soil_moisture", "value": 22.5}
    # worker يملك observation:record ⇒ ابتلاع القراءة لا يُحجب بـ403
    r = client.post(
        "/api/v1/devices/dev_x/telemetry",
        json=body,
        headers={"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"},
    )
    assert r.status_code != 403, r.text
    # viewer لا يملك observation:record ⇒ 403
    r = client.post(
        "/api/v1/devices/dev_x/telemetry",
        json=body,
        headers={"Authorization": f"Bearer {_raw_token(m, 'viewer', tenant)}"},
    )
    assert r.status_code == 403, r.text


@pytest.mark.integration
def test_bad_recorded_at_returns_400(app_mod):
    """recorded_at غير صالح يُرفَض بـ400 (تحقّق API قبل القاعدة)، وصيغة Z تُقبَل."""
    from fastapi.testclient import TestClient

    m = app_mod
    tenant = str(uuid.uuid4())
    client = TestClient(m.app)
    hdr = {"Authorization": f"Bearer {_raw_token(m, 'worker', tenant)}"}
    # تاريخ غير صالح ⇒ 400 (لا 500)
    r = client.post(
        "/api/v1/devices/dev_x/telemetry",
        json={"sensor_type": "soil_moisture", "value": 20, "recorded_at": "not-a-time"},
        headers=hdr,
    )
    assert r.status_code == 400, r.text
    assert "recorded_at" in r.text
    # صيغة Zulu صحيحة ⇒ ليست 400 (تتجاوز التحقّق؛ تصل 404/503 لغياب الجهاز/القاعدة)
    r = client.post(
        "/api/v1/devices/dev_x/telemetry",
        json={"sensor_type": "soil_moisture", "value": 20, "recorded_at": "2026-06-11T08:00:00Z"},
        headers=hdr,
    )
    assert r.status_code != 400, r.text
