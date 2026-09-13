from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

SERVICE = Path(__file__).resolve().parents[2] / "services" / "sahool-platform"
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

from api import irrigation_reservation_lifecycle_worker as worker  # noqa: E402

TENANT = UUID("11111111-1111-1111-1111-111111111111")


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Conn:
    def __init__(self):
        self.executed = []

    async def fetch(self, _sql):
        return [{"tenant_id": TENANT}]

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def transaction(self):
        return _Tx()


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


def test_sweep_scopes_tenant_and_uses_governed_expiry(monkeypatch):
    conn = _Conn()
    seen = []

    async def fake_expire(_conn, *, tenant_id):
        seen.append(tenant_id)
        return 2

    monkeypatch.setattr(worker, "expire_due", fake_expire)
    total = asyncio.run(worker.expire_all_tenants(_Pool(conn)))
    assert total == 2
    assert seen == [TENANT]
    assert any("app.current_tenant" in sql for sql, _ in conn.executed)


class _RaisingPool:
    def acquire(self):
        raise RuntimeError("pool exhausted")


def _heartbeat_in(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_HEARTBEAT_DIR", str(tmp_path))
    from api.worker_heartbeat import HeartbeatState, read_heartbeat

    return HeartbeatState(worker.WORKER_NAME), read_heartbeat


def test_a_sweep_leaves_a_fresh_running_heartbeat_the_probe_accepts(tmp_path, monkeypatch):
    """WORKERS-INHERIT-AN-HTTP-HEALTHCHECK-THEY-CANNOT-ANSWER-01: the compose probe reads this
    file; without it the worker inherits the platform image's curl :8000 check and is unhealthy
    forever. The probe's own evaluator must accept what one sweep writes."""
    from api.worker_heartbeat import evaluate_heartbeat

    hb, read = _heartbeat_in(tmp_path, monkeypatch)
    monkeypatch.setattr(worker, "expire_all_tenants", _AsyncReturn(2))
    assert asyncio.run(worker.sweep_once(_Pool(_Conn()), hb)) == 2
    data = read(worker.WORKER_NAME)
    assert data is not None and data["current_state"] == "running"
    assert data["processed_total"] == 2
    ok, reason = evaluate_heartbeat(data, now_epoch=data["last_poll_at"] + 1, max_age_seconds=120)
    assert ok, reason


def test_a_failing_sweep_marks_the_heartbeat_failed_but_keeps_the_worker_alive(
    tmp_path, monkeypatch
):
    from api.worker_heartbeat import evaluate_heartbeat

    hb, read = _heartbeat_in(tmp_path, monkeypatch)
    # No exception escapes (liveness preserved) …
    assert asyncio.run(worker.sweep_once(_RaisingPool(), hb)) == 0
    data = read(worker.WORKER_NAME)
    # … and the probe reports the failure with its text rather than a silent green.
    assert data is not None and data["current_state"] == "failed"
    assert "pool exhausted" in data["last_error"]
    ok, reason = evaluate_heartbeat(data, now_epoch=data["last_poll_at"] + 1, max_age_seconds=120)
    assert not ok and reason.startswith("worker_state_failed:")


class _AsyncReturn:
    def __init__(self, value):
        self.value = value

    async def __call__(self, *_a, **_k):
        return self.value


def test_poll_interval_is_fail_safe(monkeypatch):
    monkeypatch.setenv("IRRIGATION_RESERVATION_LIFECYCLE_POLL_SECONDS", "bad")
    assert worker.poll_seconds() == 15.0
    monkeypatch.setenv("IRRIGATION_RESERVATION_LIFECYCLE_POLL_SECONDS", "0")
    assert worker.poll_seconds() == 1.0
