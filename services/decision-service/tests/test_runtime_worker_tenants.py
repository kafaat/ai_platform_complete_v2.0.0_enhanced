"""WX-12 multitenancy: server-authorized worker→tenant partitioning on real Postgres.

Includes the forensic-hardening proofs (73666ee audit): fail-closed strict mode for
unknown workers (F-01), stale-idempotency replay safety via the append-only command
ledger (F-02/F-06), and the identifier/hash CHECK constraints (F-07).
"""

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


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _payload(tenant: str, key: str, enabled: bool = True):
    return SimpleNamespace(tenant_id=tenant, enabled=enabled, idempotency_key=key)


def _register(worker: str, tenant: str, key: str, enabled: bool = True):
    from persistence import register_runtime_worker_tenant

    return _run(
        register_runtime_worker_tenant(
            worker_id=worker, created_by="ops", payload=_payload(tenant, key, enabled)
        )
    )


def test_registration_replay_conflict_and_authorization_partitioning():
    from persistence import list_worker_tenants, worker_tenant_authorized

    worker = "adapter-" + uuid4().hex[:8]

    # unregistered worker keeps the legacy behavior (deployment pins the tenant via env).
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_A)) is True

    key = "reg_" + uuid4().hex
    first = _register(worker, TENANT_A, key)
    assert first["status"] == "ok" and first["replay"] is False and first["enabled"] is True
    assert first["revision"] == 1 and first["command_id"].startswith("wtc_")

    # identical retry replays the ORIGINAL command outcome; a different payload under
    # the same key is a typed conflict.
    replay = _register(worker, TENANT_A, key)
    assert replay["status"] == "ok" and replay["replay"] is True
    assert replay["command_id"] == first["command_id"] and replay["revision"] == 1
    conflict = _register(worker, TENANT_B, key)
    assert conflict == {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}

    # once registered, only the enabled tenants pass — free header picking is over.
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_A)) is True
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_B)) is False

    listed = _run(list_worker_tenants(worker_id=worker))
    assert listed["registered"] is True and listed["tenants"] == [TENANT_A]

    # disabling a registration revokes the tenant without deleting the audit trail,
    # and the projection revision advances monotonically.
    disabled = _register(worker, TENANT_A, "reg_" + uuid4().hex, enabled=False)
    assert disabled["revision"] == 2 and disabled["enabled"] is False
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_A)) is False
    assert _run(list_worker_tenants(worker_id=worker))["tenants"] == []


def test_stale_replay_cannot_resurrect_revocation():
    """F-02: a delayed retry of an old 'enable' must NOT undo a later revocation."""
    from persistence import worker_tenant_authorized

    worker = "adapter-" + uuid4().hex[:8]
    key_enable = "reg_" + uuid4().hex
    key_disable = "reg_" + uuid4().hex

    assert _register(worker, TENANT_A, key_enable)["revision"] == 1
    assert _register(worker, TENANT_A, key_disable, enabled=False)["revision"] == 2
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_A)) is False

    # the stale retry reports its ORIGINAL outcome (enabled@rev1)...
    stale = _register(worker, TENANT_A, key_enable)
    assert stale["replay"] is True and stale["enabled"] is True and stale["revision"] == 1

    # ...but the projection stays revoked at revision 2: revocation is final.
    assert _run(worker_tenant_authorized(worker_id=worker, tenant_id=TENANT_A)) is False

    async def projection():
        c = await _connect()
        try:
            return await c.fetchrow(
                "SELECT enabled, revision FROM decision_runtime_worker_tenants"
                " WHERE worker_id=$1 AND tenant_id=$2::uuid",
                worker,
                TENANT_A,
            )
        finally:
            await c.close()

    row = _run(projection())
    assert row["enabled"] is False and row["revision"] == 2


def test_strict_mode_denies_unknown_workers(monkeypatch):
    """F-01: with DECISION_STRICT_WORKER_TENANTS on, unregistered workers get NOTHING."""
    from persistence import worker_tenant_authorized

    unknown = "adapter-" + uuid4().hex[:8]
    registered = "adapter-" + uuid4().hex[:8]
    _register(registered, TENANT_A, "reg_" + uuid4().hex)

    monkeypatch.setenv("DECISION_STRICT_WORKER_TENANTS", "true")
    assert _run(worker_tenant_authorized(worker_id=unknown, tenant_id=TENANT_A)) is False
    assert _run(worker_tenant_authorized(worker_id=unknown, tenant_id=TENANT_B)) is False
    # registered mappings keep working exactly as before.
    assert _run(worker_tenant_authorized(worker_id=registered, tenant_id=TENANT_A)) is True
    assert _run(worker_tenant_authorized(worker_id=registered, tenant_id=TENANT_B)) is False

    monkeypatch.delenv("DECISION_STRICT_WORKER_TENANTS")
    assert _run(worker_tenant_authorized(worker_id=unknown, tenant_id=TENANT_A)) is True


def test_command_ledger_is_append_only_with_constraint_checks():
    """F-06/F-07: ledger rows are immutable and identifier/hash CHECKs hold at the row."""

    async def attempt(sql, *args):
        c = await _connect()
        try:
            await c.execute(sql, *args)
            return "ok"
        except Exception as exc:  # noqa: BLE001 - the assertion IS about the raised class
            return type(exc).__name__
        finally:
            await c.close()

    insert = """INSERT INTO decision_runtime_worker_tenant_commands
       (command_id, worker_id, tenant_id, requested_enabled, created_by,
        idempotency_key, request_hash, resulting_revision)
       VALUES ($1, $2, $3::uuid, true, $4, $5, $6, 1)"""

    # malformed request_hash (not 64 lowercase hex) is refused by the row CHECK.
    out = _run(
        attempt(
            insert,
            "wtc_" + uuid4().hex[:12],
            "w-" + uuid4().hex[:6],
            TENANT_A,
            "ops",
            "k_" + uuid4().hex,
            "NOT-A-SHA",
        )
    )
    assert out == "CheckViolationError"

    # blank worker_id is refused.
    out = _run(
        attempt(
            insert,
            "wtc_" + uuid4().hex[:12],
            "   ",
            TENANT_A,
            "ops",
            "k_" + uuid4().hex,
            "a" * 64,
        )
    )
    assert out == "CheckViolationError"

    # a valid ledger row can neither be updated nor deleted (append-only trigger).
    cmd_id = "wtc_" + uuid4().hex[:12]
    worker = "w-" + uuid4().hex[:6]
    key = "k_" + uuid4().hex
    assert _run(attempt(insert, cmd_id, worker, TENANT_A, "ops", key, "a" * 64)) == "ok"
    out = _run(
        attempt(
            "UPDATE decision_runtime_worker_tenant_commands SET requested_enabled=false"
            " WHERE command_id=$1",
            cmd_id,
        )
    )
    assert out != "ok"
    out = _run(
        attempt("DELETE FROM decision_runtime_worker_tenant_commands WHERE command_id=$1", cmd_id)
    )
    assert out != "ok"

    # the same (worker, idempotency_key) can never land twice in the ledger.
    out = _run(attempt(insert, "wtc_" + uuid4().hex[:12], worker, TENANT_A, "ops", key, "b" * 64))
    assert out == "UniqueViolationError"


def test_feed_enforces_worker_partition_end_to_end(monkeypatch):
    """HTTP proof: a registered worker gets 403 for a non-authorized tenant, 200 for
    its own; in strict mode an UNKNOWN worker is denied outright (fail-closed)."""
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
    body = reg.json()
    assert body["revision"] == 1 and body["command_id"].startswith("wtc_")

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

    # strict mode over HTTP: an unknown worker_id no longer bypasses the registry.
    monkeypatch.setenv("DECISION_STRICT_WORKER_TENANTS", "1")
    stranger = client.get(
        "/v1/learning/runtime-work",
        params={"worker_id": "adapter-" + uuid4().hex[:8], "limit": 5},
        headers={"X-Tenant-Id": TENANT_A},
    )
    assert stranger.status_code == 403
    assert stranger.json()["detail"]["code"] == "worker_tenant_unauthorized"
