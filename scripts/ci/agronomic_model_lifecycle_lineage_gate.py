#!/usr/bin/env python3
"""Cohort lineage gate: evaluation → promotion → activation must carry the cohorts intact."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERSISTENCE = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
MIGRATION = ROOT / "services/decision-service/migrations/021_model_agronomic_cohort_lineage.sql"

required_code = [
    "_agronomic_cohort_manifest",
    "_agronomic_cohort_fingerprint",
    "d.agronomic_context_snapshot_id",
    'evaluation["agronomic_cohorts"]',
    'promotion["agronomic_cohorts"]',
]
missing = [token for token in required_code if token not in PERSISTENCE]
if not MIGRATION.exists():
    missing.append(str(MIGRATION.relative_to(ROOT)))
else:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "enforce_model_promotion_cohort_lineage",
        "enforce_model_activation_cohort_lineage",
    ):
        if token not in sql:
            missing.append(token)
if missing:
    raise SystemExit("agronomic model lifecycle lineage gate FAILED: " + ", ".join(missing))
print("agronomic model lifecycle lineage gate: PASS")
