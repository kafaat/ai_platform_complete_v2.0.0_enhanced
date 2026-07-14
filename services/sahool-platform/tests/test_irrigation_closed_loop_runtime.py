from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api import irrigation_closed_loop_runtime as mod

D = "a" * 64
RUN = "00000000-0000-0000-0000-000000000001"


class FakeConn:
    def __init__(self):
        self.reconciliation = None
        self.writes = []

    async def fetchrow(self, sql, *args):
        now = datetime.now(UTC)
        if "as_applied_irrigation_runs" in sql:
            return {
                "id": RUN,
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "field_id": "field-1",
                "season_id": "season-1",
                "machine_id": "22222222-2222-2222-2222-222222222222",
                "controller_id": "33333333-3333-3333-3333-333333333333",
                "decision_id": "decision-1",
                "authorization_id": "auth-1",
                "execution_plan_id": "plan-1",
                "planned_start_at": now - timedelta(minutes=20),
                "planned_end_at": now - timedelta(minutes=5),
                "planned_depth_mm": 1.2,
                "planned_volume_m3": 60.0,
                "planned_area_ha": 5.0,
                "irrigation_capability_digest": D,
                "commissioning_certification_digest": D,
                "decision_content_digest": D,
                "created_at": now - timedelta(minutes=20),
            }
        if "irrigation_water_ledger_reconciliations" in sql:
            return None
        return None

    async def fetch(self, sql, *args):
        now = datetime.now(UTC)
        if "as_applied_irrigation_receipts" in sql:
            return [
                {
                    "controller_id": "33333333-3333-3333-3333-333333333333",
                    "receipt_id": "r1",
                    "state": "completed",
                    "sequence_number": 1,
                    "observed_at": now - timedelta(minutes=2),
                    "controller_command_digest": D,
                    "payload_digest": D,
                }
            ]
        values = [
            ("flow", 50.0, "lps"),
            ("pressure", 2.5, "bar"),
            ("runtime", 20.0, "minutes"),
            ("position", 0.0, "percent"),
            ("position", 100.0, "percent"),
        ]
        return [
            {
                "controller_id": "33333333-3333-3333-3333-333333333333",
                "observation_type": kind,
                "sequence_number": i + 1,
                "observed_at": now - timedelta(minutes=6 - i),
                "value": value,
                "unit": unit,
                "source_message_id": f"m{i}",
                "payload_digest": D,
            }
            for i, (kind, value, unit) in enumerate(values)
        ]

    async def fetchval(self, sql, *args):
        return 20.0

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


@pytest.mark.asyncio
async def test_verified_run_reconciles_measured_water():
    conn = FakeConn()
    out = await mod.reconcile_irrigation_run(conn, run_id=RUN, now=datetime.now(UTC))
    assert out["status"] == "reconciled"
    assert out["reconciled"] is True
    assert out["applied_depth_mm"] == pytest.approx(1.2)
    assert out["depletion_after_mm"] == pytest.approx(18.8)
    assert any("INSERT INTO water_ledger" in sql for sql, _ in conn.writes)


@pytest.mark.asyncio
async def test_missing_run_fails_closed():
    class Missing(FakeConn):
        async def fetchrow(self, sql, *args):
            if "as_applied_irrigation_runs" in sql:
                return None
            return await super().fetchrow(sql, *args)

    out = await mod.reconcile_irrigation_run(Missing(), run_id=RUN)
    assert out == {"status": "blocked", "reason": "AS_APPLIED_RUN_NOT_FOUND"}
