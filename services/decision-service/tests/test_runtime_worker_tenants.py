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


def test_worker_assertion_identity_binding_enforced_at_endpoint(monkeypatch):
    """HTTP+PG proof that WITH assertion enforcement ON the worker-identity binding gates the
    REAL endpoints (not just the pure verifier): a worker pulls only its OWN feed with a valid
    request-scoped assertion; claiming another worker's id, or an absent/forged assertion, is
    403; and the identity + tenant-partition controls COMPOSE — a valid identity still cannot
    cross into an unauthorized tenant. Complements test_feed_enforces_worker_partition_end_to_end
    (which runs assertion-off, proving the partition alone)."""
    import importlib.util

    from fastapi.testclient import TestClient

    from shared.security.service_tenant_assertion import create_tenant_assertion

    key = "worker-endpoint-assertion-key-at-least-32-chars!!"
    # Enforcement ON (key set); development so the replay store is a no-op without Redis (the
    # replay/503 path is proven separately in test_worker_identity_binding.py). Verification runs.
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_KEY", key)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.delenv("DECISION_WORKER_ASSERTION_REDIS_URL", raising=False)

    spec = importlib.util.spec_from_file_location("decision_wid_main", SERVICE_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    client = TestClient(mod.app)

    worker_a = "adapter-" + uuid4().hex[:8]
    worker_b = "adapter-" + uuid4().hex[:8]
    feed = "/v1/learning/runtime-work"

    # Operator registers each worker to its own tenant (X-Registered-By; registration is not
    # worker-authenticated — a worker cannot self-authorize its tenants).
    for w, t in ((worker_a, TENANT_A), (worker_b, TENANT_B)):
        reg = client.post(
            f"/v1/learning/runtime-workers/{w}/tenants",
            headers={"X-Registered-By": "ops"},
            json={"tenant_id": t, "enabled": True, "idempotency_key": "reg_" + uuid4().hex},
        )
        assert reg.status_code == 200, reg.text

    def sign(subject, *, request_id, method="GET", path=feed, k=key, key_id="current"):
        return create_tenant_assertion(
            k,
            mod.WORKER_ASSERTION_SERVICE,
            subject,
            key_id=key_id,
            method=method,
            path=path,
            request_id=request_id,
        )

    # 1) Worker A with a valid, request-scoped assertion pulls its OWN feed → 200.
    ok = client.get(
        feed,
        params={"worker_id": worker_a, "limit": 5},
        headers={
            "X-Tenant-Id": TENANT_A,
            "X-Request-Id": "r-a1",
            "X-Worker-Assertion": sign(worker_a, request_id="r-a1"),
        },
    )
    assert ok.status_code == 200, ok.text

    # 2) Impersonation blocked: caller presents worker_id=B (to reach B's partition) but only
    #    holds A's assertion (subject A ≠ presented B) → 403. Worker A cannot pull worker B's feed.
    imp = client.get(
        feed,
        params={"worker_id": worker_b, "limit": 5},
        headers={
            "X-Tenant-Id": TENANT_B,
            "X-Request-Id": "r-imp",
            "X-Worker-Assertion": sign(worker_a, request_id="r-imp"),
        },
    )
    assert imp.status_code == 403, imp.text
    assert "worker assertion" in str(imp.json()["detail"]).lower()

    # 3) Absent assertion while enforcement is ON → 403 (no header-only free pick).
    absent = client.get(
        feed,
        params={"worker_id": worker_a, "limit": 5},
        headers={"X-Tenant-Id": TENANT_A, "X-Request-Id": "r-abs"},
    )
    assert absent.status_code == 403, absent.text

    # 4) Forged assertion (correct kid, wrong signing key) → 403.
    forged = client.get(
        feed,
        params={"worker_id": worker_a, "limit": 5},
        headers={
            "X-Tenant-Id": TENANT_A,
            "X-Request-Id": "r-fg",
            "X-Worker-Assertion": sign(
                worker_a, request_id="r-fg", k="a-different-worker-key-at-least-32-chars!"
            ),
        },
    )
    assert forged.status_code == 403, forged.text

    # 5) Controls compose: a VALID identity for A still cannot cross into an unauthorized tenant —
    #    the tenant partition is enforced independently → 403 worker_tenant_unauthorized.
    cross = client.get(
        feed,
        params={"worker_id": worker_a, "limit": 5},
        headers={
            "X-Tenant-Id": TENANT_B,
            "X-Request-Id": "r-x",
            "X-Worker-Assertion": sign(worker_a, request_id="r-x"),
        },
    )
    assert cross.status_code == 403, cross.text
    assert cross.json()["detail"]["code"] == "worker_tenant_unauthorized"

    # 6) Discovery is identity-bound too: A enumerates only ITS OWN partition with a path-bound
    #    assertion (→ 200 [TENANT_A]); a caller cannot discover worker B's partition with A's
    #    assertion → 403 (no cross-worker tenant enumeration).
    disc_a = f"/v1/learning/runtime-workers/{worker_a}/tenants"
    disc_ok = client.get(
        disc_a,
        headers={
            "X-Request-Id": "r-d1",
            "X-Worker-Assertion": sign(worker_a, path=disc_a, request_id="r-d1"),
        },
    )
    assert disc_ok.status_code == 200, disc_ok.text
    assert disc_ok.json()["tenants"] == [TENANT_A]

    disc_b = f"/v1/learning/runtime-workers/{worker_b}/tenants"
    disc_imp = client.get(
        disc_b,
        headers={
            "X-Request-Id": "r-d2",
            "X-Worker-Assertion": sign(worker_a, path=disc_a, request_id="r-d2"),
        },
    )
    assert disc_imp.status_code == 403, disc_imp.text
