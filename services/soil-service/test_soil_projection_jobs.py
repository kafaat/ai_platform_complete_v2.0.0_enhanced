from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "soil_projection_jobs", ROOT / "services/soil-service/projection_jobs.py"
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


class FakeConn:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "INSERT 0 1"


class FakePool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "UPDATE 1"


async def test_enqueue_is_coalesced_by_active_field():
    conn = FakeConn()
    await module.enqueue(
        conn, tenant_id="00000000-0000-0000-0000-000000000001", field_id="F1", reason="test"
    )
    sql, args = conn.calls[0]
    assert "ON CONFLICT (tenant_id, field_id)" in sql
    assert "pending','running','retry" in sql
    assert args[-2:] == ("F1", "test")


async def test_failure_moves_terminal_job_to_dead_letter(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(module, "MAX_ATTEMPTS", 3)
    await module.fail(pool, job_id=9, attempts=3, error="boom")
    _sql, args = pool.calls[0]
    assert args[1] == "dead_letter"
    assert args[3] == "boom"


async def test_failure_retries_before_attempt_budget(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(module, "MAX_ATTEMPTS", 4)
    await module.fail(pool, job_id=9, attempts=2, error="temporary")
    _sql, args = pool.calls[0]
    assert args[1] == "retry"
    assert 1 <= args[2] <= 900
