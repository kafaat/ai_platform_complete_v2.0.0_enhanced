"""WX-12 multitenancy: server-authorized worker→tenant partitioning on real Postgres."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")

TENANT_A = "00000000-0000-0000-0000-000000009171"
TENANT_B = "00000000-0000-0000-0000-000000009172"


def _run(c):
    return asyncio.run(c)


def _payload(tenant: str, key: str, enabled: bool = True):
    return SimpleNamespace(tenant_id=tenant, enabled=enabled, idempotency_key=key)


def test_registration_replay_conflict_and_authorization_partitioning():
    from persistence import (
        list_worker_tenants,
        register_runtime_worker_tenant,
        worker_tenant_authorized,
    )

    worker = "adapter-" + uuid4().hex[:8]

    # unregistered worker keeps the legacy behavior (deployment pins the tenant via env).
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_A)) is True

    key = "reg_" + uuid4().hex
    first = _run(
        register_runtime_worker_tenant(
            worker_id=worker, created_by="ops", payload=_payload(TENANT_A, key)
        )
    )
    assert first["status"] == "ok" and first["replay"] is False and first["enabled"] is True

    # identical retry replays; a different payload under the same key is a typed conflict.
    replay = _run(
        register_runtime_worker_tenant(
            worker_id=worker, created_by="ops", payload=_payload(TENANT_A, key)
        )
    )
    assert replay["status"] == "ok" and replay["replay"] is True
    conflict = _run(
        register_runtime_worker_tenant(
            worker_id=worker, created_by="ops", payload=_payload(TENANT_B, key)
        )
    )
    assert conflict == {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}

    # once registered, only the enabled tenants pass — free header picking is over.
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_A)) is True
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_B)) is False

    listed = _run(list_worker_tenants(worker_id=worker))
    assert listed["registered"] is True and listed["tenants"] == [TENANT_A]

    # disabling a registration revokes the tenant without deleting the audit row.
    _run(
        register_runtime_worker_tenant(
            worker_id=worker,
            created_by="ops",
            payload=_payload(TENANT_A, "reg_" + uuid4().hex, enabled=False),
        )
    )
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_A)) is False
    assert _run(list_worker_tenants(worker_id=worker))["tenants"] == []


def test_feed_enforces_worker_partition_end_to_end():
    """HTTP proof: a registered worker gets 403 for a non-authorized tenant, 200 for its own."""
    import importlib.util

    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location("decision_mt_main", SERVICE_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    client = TestClient(mod.app)

    worker = "adapter-" + uuid4().hex[:8]
    reg = client.post(
        f"/v1/learning/runtime-workers/{worker}/tenants",
        headers={"X-Registered-By": "ops"},
        json={"tenant_id": TENANT_A, "enabled": True, "idempotency_key": "reg_" + uuid4().hex},
    )
    assert reg.status_code == 200, reg.text

    ok = client.get(
        "/v1/learning/runtime-work",
        params={"worker_id": worker, "limit": 5},
        headers={"X-Tenant-Id": TENANT_A},
    )
    assert ok.status_code == 200

    denied = client.get(
        "/v1/learning/runtime-work",
        params={"worker_id": worker, "limit": 5},
        headers={"X-Tenant-Id": TENANT_B},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "worker_tenant_unauthorized"

    # discovery: the worker enumerates its authorized partition from the server.
    disc = client.get(f"/v1/learning/runtime-workers/{worker}/tenants")
    assert disc.status_code == 200
    assert disc.json()["tenants"] == [TENANT_A]
