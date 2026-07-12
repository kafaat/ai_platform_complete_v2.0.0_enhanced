#!/usr/bin/env python3
"""Terminal lineage gate: rollback/rollout/dispatch receipts + rollback-aware monitoring."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
persistence = (ROOT / "services/decision-service/persistence.py").read_text()
migration = (
    ROOT / "services/decision-service/migrations/023_runtime_terminal_agronomic_lineage.sql"
).read_text()
required = [
    "source_transition_type",
    "decision_assert_rollback_command_cohorts",
    "decision_assert_rollback_receipt_cohorts",
    "decision_assert_rollout_receipt_cohorts",
    "decision_assert_retraining_dispatch_cohorts",
]
missing = [x for x in required if x not in migration]
assert not missing, f"migration 023 missing: {missing}"
for token in (
    'plan["agronomic_cohorts"]',
    'request["agronomic_cohorts"]',
    'command["agronomic_cohorts"]',
    'active["source_transition_type"]',
):
    assert token in persistence, f"persistence missing {token}"
print("Agronomic runtime terminal lineage gate: PASS")
