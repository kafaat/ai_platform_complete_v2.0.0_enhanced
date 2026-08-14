#!/usr/bin/env python3
"""Ratchet for durable measured irrigation reconciliation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
service = (ROOT / "services/sahool-platform/api/irrigation_closed_loop_runtime.py").read_text(
    encoding="utf-8"
)
migration = (ROOT / "migrations/v184_irrigation_closed_loop_runtime_reconciliation.sql").read_text(
    encoding="utf-8"
)
router = (ROOT / "services/sahool-platform/api/routers/irrigation_mpc.py").read_text(
    encoding="utf-8"
)
for token in (
    "build_canonical_as_applied_irrigation_truth",
    "as_applied_truth_to_water_ledger_event",
    "pg_advisory_xact_lock",
    "irrigation_water_ledger_reconciliations",
    "measured_as_applied",
    "ON CONFLICT",
):
    assert token in service, token
for token in (
    "ENABLE ROW LEVEL SECURITY",
    "FORCE ROW LEVEL SECURITY",
    "UNIQUE (tenant_id, as_applied_digest)",
    "WITH CHECK",
):
    assert token in migration, token
assert "/api/v1/irrigation/executions/reconcile" in router
for forbidden in ("mqtt.publish", "modbus.write", "actuator dispatch"):
    assert forbidden not in service.lower(), forbidden
print("irrigation closed-loop runtime guard: PASS")
