#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = {
    "services/sahool-platform/api/irrigation_manual_ledger_bridge.py": [
        "verify_manual_as_applied",
        "build_manual_water_ledger_event",
        "ONLY_MANUAL_MEASURED_CAN_BE_VERIFIED_FOR_LEDGER",
    ],
    "services/sahool-platform/api/routers/irrigation_engineering.py": [
        "/manual-executions/{execution_id}/verify",
        "/manual-executions/{execution_id}/reconcile",
        "USE_GOVERNED_VERIFY_OR_RECONCILE_ENDPOINT",
        "pg_advisory_xact_lock",
    ],
    "migrations/v188_irrx1_verified_manual_as_applied_ledger_bridge.sql": [
        "irrigation_manual_ledger_reconciliations",
        "FORCE ROW LEVEL SECURITY",
        "WITH CHECK",
        "append-only",
        "UNIQUE (tenant_id, execution_id)",
    ],
}
for rel, needles in required.items():
    p = ROOT / rel
    assert p.exists(), f"missing {rel}"
    text = p.read_text(encoding="utf-8")
    for needle in needles:
        assert needle in text, f"{rel} missing {needle}"
print("IRR-X1.3 verified manual as-applied ledger guard: PASS")
