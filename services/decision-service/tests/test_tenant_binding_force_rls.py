"""Every read path over a FORCE-RLS decision table binds its identity first.

Migration 037 forces row-level security on the last 32 decision tables with a tenant_id
column (the v206 catalog assertion). Under FORCE the policies apply to the owning runtime
role, so a query that filters ``tenant_id=$1`` but never binds ``app.current_tenant``
silently returns no rows and fails every WITH CHECK. ``set_config(..., true)`` is
transaction-local, so the binding only counts when it is issued inside the same
transaction as the queries it scopes.

These tests drive each previously unbound function against a recording fake connection
and assert: (1) a transaction is open before the first statement, (2) the first statement
is the identity binding with the caller's value, and (3) every later statement runs inside
that transaction. The live PostgreSQL proof is ``test_force_rls_live_pg.py``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import persistence  # noqa: E402

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000000037"
WORKER = "registry-adapter-037"
BIND_TENANT = "SELECT set_config('app.current_tenant', $1, true)"
BIND_WORKER = "SELECT set_config('app.current_worker', $1, true)"


class _Tx:
    def __init__(self, conn: _RecordingConn) -> None:
        self._conn = conn

    async def __aenter__(self):
        self._conn.depth += 1
        self._conn.log.append(("tx_begin", None, ()))
        return self

    async def __aexit__(self, *exc):
        self._conn.depth -= 1
        self._conn.log.append(("tx_end", None, ()))
        return False


class _RecordingConn:
    """Records every statement with the transaction depth it ran at."""

    def __init__(self, *, fetch=None, fetchrow=None, fetchval=None) -> None:
        self.depth = 0
        self.log: list[tuple[str, Any, tuple]] = []
        self.statements: list[tuple[str, str, tuple, int]] = []
        self._fetch = list(fetch or [])
        self._fetchrow = list(fetchrow or [])
        self._fetchval = list(fetchval or [])
        self.closed = False

    def transaction(self, **_kwargs):
        return _Tx(self)

    def _record(self, kind: str, sql: str, args: tuple) -> None:
        self.statements.append((kind, sql, args, self.depth))
        self.log.append((kind, sql, args))

    async def execute(self, sql, *args):
        self._record("execute", sql, args)
        return "OK"

    async def fetch(self, sql, *args):
        self._record("fetch", sql, args)
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql, *args):
        self._record("fetchrow", sql, args)
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, sql, *args):
        self._record("fetchval", sql, args)
        return self._fetchval.pop(0) if self._fetchval else None

    async def close(self):
        self.closed = True


def _install(monkeypatch, conn: _RecordingConn) -> _RecordingConn:
    async def _connect():
        return conn

    monkeypatch.setattr(persistence, "_connect", _connect)
    return conn


def _assert_bound_first(conn: _RecordingConn, *bindings: tuple[str, str]) -> None:
    assert conn.statements, "the function issued no statement at all"
    head = conn.statements[: len(bindings)]
    assert len(head) == len(bindings), "fewer statements than required bindings"
    for (kind, sql, args, depth), (expected_sql, expected_value) in zip(
        head, bindings, strict=True
    ):
        assert kind == "execute"
        assert sql == expected_sql
        assert args == (expected_value,)
        assert depth >= 1, "set_config(..., true) outside a transaction is a no-op"
    for kind, sql, _args, depth in conn.statements:
        assert depth >= 1, f"statement ran outside the bound transaction: {kind} {sql[:80]}"
    assert conn.closed


def _run(coro):
    return asyncio.run(coro)


def test_get_context_snapshot_binds_tenant(monkeypatch):
    conn = _install(monkeypatch, _RecordingConn())
    out = _run(persistence.get_context_snapshot(tenant_id=TENANT, snapshot_id="ctx_1"))
    assert out == {"status": "not_found"}
    _assert_bound_first(conn, (BIND_TENANT, TENANT))
    assert "decision_agronomic_context_snapshots" in conn.statements[1][1]


def test_get_decision_agronomic_evidence_binds_tenant_for_every_read(monkeypatch):
    decision = {
        "decision_id": "dec_1",
        "decision_value": "{}",
        "created_at": "2026-11-12T00:00:00Z",
        "agronomic_context_snapshot_id": "ctx_1",
        "field_historical_context_snapshot_id": None,
        "feature_manifest_id": "fm_1",
        "feature_manifest_hash": None,
        "vegetation_snapshot_id": None,
        "context_contract_version": "legacy_unbound",
    }
    conn = _install(monkeypatch, _RecordingConn(fetchrow=[decision, None, None]))
    out = _run(persistence.get_decision_agronomic_evidence(tenant_id=TENANT, decision_id="dec_1"))
    assert out["status"] == "ok"
    _assert_bound_first(conn, (BIND_TENANT, TENANT))
    tables = " ".join(sql for _k, sql, _a, _d in conn.statements[1:])
    for table in (
        "decision_record",
        "decision_agronomic_context_snapshots",
        "decision_feature_manifests",
    ):
        assert table in tables


def test_build_calibration_dataset_binds_tenant(monkeypatch):
    conn = _install(monkeypatch, _RecordingConn())
    out = _run(
        persistence.build_calibration_dataset(
            tenant_id=TENANT, model_id="m1", feature_set_id=None, limit=10
        )
    )
    assert out["count"] == 0
    _assert_bound_first(conn, (BIND_TENANT, TENANT))
    assert "decision_learning_attributions" in conn.statements[1][1]


def test_list_queued_execution_requests_binds_tenant(monkeypatch):
    conn = _install(monkeypatch, _RecordingConn())
    out = _run(persistence.list_queued_execution_requests(tenant_id=TENANT))
    assert out["count"] == 0
    _assert_bound_first(conn, (BIND_TENANT, TENANT))
    assert "decision_execution_requests" in conn.statements[1][1]


def test_list_inflight_execution_requests_binds_tenant(monkeypatch):
    conn = _install(monkeypatch, _RecordingConn())
    out = _run(persistence.list_inflight_execution_requests(tenant_id=TENANT, adapter_id="a1"))
    assert out["count"] == 0
    _assert_bound_first(conn, (BIND_TENANT, TENANT))
    assert "decision_execution_delivery_attempts" in conn.statements[1][1]


def test_get_active_model_state_binds_tenant(monkeypatch):
    conn = _install(monkeypatch, _RecordingConn())
    out = _run(
        persistence.get_active_model_state(
            tenant_id=TENANT, model_id="m1", feature_set_id=None, target_environment="staging"
        )
    )
    assert out == {"status": "not_found"}
    _assert_bound_first(conn, (BIND_TENANT, TENANT))
    assert "decision_model_registry_activation_receipts" in conn.statements[1][1]


def test_list_runtime_work_binds_tenant_and_leases_inside_the_transaction(monkeypatch):
    row = {
        "work_type": "retraining_dispatch",
        "payload": {"retraining_request_id": "rt_1", "model_id": "m1"},
    }
    conn = _install(monkeypatch, _RecordingConn(fetch=[[row]], fetchval=["wkclaim_x"]))
    out = _run(persistence.list_runtime_work(tenant_id=TENANT, worker_id=WORKER))
    assert [item["work_type"] for item in out["items"]] == ["retraining_dispatch"]
    _assert_bound_first(conn, (BIND_TENANT, TENANT))
    lease = [s for s in conn.statements if "decision_model_runtime_work_claims" in s[1]]
    assert lease and all(depth >= 1 for _k, _s, _a, depth in lease)


def test_reservation_inbox_binds_tenant_before_the_dedup_read(monkeypatch):
    prior = {"request_hash": "not-the-same-hash"}
    conn = _install(monkeypatch, _RecordingConn(fetchrow=[prior]))
    out = _run(
        persistence.record_reservation_dispatch_intent(
            tenant_id=TENANT,
            source_event_id="evt_1",
            event_type="irrigation.reservation.dispatch_requested",
            payload=SimpleNamespace(evaluation_id="ev_1", reservation_ids=["r1"]),
        )
    )
    assert out == {"status": "conflict", "reason": "source_event_payload_mismatch"}
    _assert_bound_first(conn, (BIND_TENANT, TENANT))
    assert "decision_reservation_dispatch_inbox" in conn.statements[1][1]


def test_list_worker_tenants_binds_worker(monkeypatch):
    rows = [
        {"tenant_id": TENANT, "enabled": True},
        {"tenant_id": "00000000-0000-0000-0000-000000000038", "enabled": False},
    ]
    conn = _install(monkeypatch, _RecordingConn(fetch=[rows]))
    out = _run(persistence.list_worker_tenants(worker_id=WORKER))
    assert out == {"worker_id": WORKER, "registered": True, "tenants": [TENANT]}
    _assert_bound_first(conn, (BIND_WORKER, WORKER))


@pytest.mark.parametrize("strict", [False, True])
def test_worker_tenant_authorized_probes_registration_under_worker_binding(monkeypatch, strict):
    """A registered worker never reaches the legacy 'unregistered -> allow' branch."""
    monkeypatch.setenv("DECISION_STRICT_WORKER_TENANTS", "true" if strict else "")
    # registered (probe returns 1) but not for this tenant (second probe returns None)
    conn = _install(monkeypatch, _RecordingConn(fetchval=[1, None]))
    assert _run(persistence.worker_tenant_authorized(worker_id=WORKER, tenant_id=TENANT)) is False
    _assert_bound_first(conn, (BIND_WORKER, WORKER))
    assert len(conn.statements) == 3  # bind + registration probe + tenant probe

    conn = _install(monkeypatch, _RecordingConn(fetchval=[1, 1]))
    assert _run(persistence.worker_tenant_authorized(worker_id=WORKER, tenant_id=TENANT)) is True
    _assert_bound_first(conn, (BIND_WORKER, WORKER))


def test_worker_tenant_authorized_unregistered_keeps_mode_semantics(monkeypatch):
    monkeypatch.setenv("DECISION_STRICT_WORKER_TENANTS", "true")
    conn = _install(monkeypatch, _RecordingConn(fetchval=[None]))
    assert _run(persistence.worker_tenant_authorized(worker_id=WORKER, tenant_id=TENANT)) is False
    _assert_bound_first(conn, (BIND_WORKER, WORKER))


def test_register_worker_tenant_binds_tenant_and_worker_before_replay_lookup(monkeypatch):
    prior = {"request_hash": "different"}
    conn = _install(monkeypatch, _RecordingConn(fetchrow=[prior]))
    payload = SimpleNamespace(tenant_id=TENANT, enabled=True, idempotency_key="k1")
    out = _run(
        persistence.register_runtime_worker_tenant(
            worker_id=WORKER, created_by="operator", payload=payload
        )
    )
    assert out == {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}
    _assert_bound_first(conn, (BIND_TENANT, TENANT), (BIND_WORKER, WORKER))
    assert "decision_runtime_worker_tenant_commands" in conn.statements[2][1]
