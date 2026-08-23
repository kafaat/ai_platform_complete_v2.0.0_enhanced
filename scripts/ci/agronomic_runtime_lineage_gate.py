#!/usr/bin/env python3
"""Runtime cohort lineage gate: monitoring/retraining stay bound to authoritative upstream."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
M = (
    ROOT / "services/decision-service/migrations/022_runtime_agronomic_cohort_lineage.sql"
).read_text(encoding="utf-8")
P = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
MAIN = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
required = [
    "decision_model_monitoring_snapshots",
    "source_receipt_id",
    "source_monitoring_snapshot_id",
    "decision_assert_monitoring_cohorts",
    "decision_assert_retraining_cohorts",
    "agronomic_cohort_fingerprint",
    "active_model_receipt_required",
    "retraining_requires_drift_signal",
]
missing = [x for x in required if x not in M + P + MAIN]
if missing:
    raise SystemExit("missing runtime agronomic lineage markers: " + ", ".join(missing))
print("agronomic runtime lineage gate: PASS")
