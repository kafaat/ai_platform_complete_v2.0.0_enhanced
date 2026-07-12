#!/usr/bin/env python3
"""AC-9 gate: governed agronomic evidence must keep propagating into learning datasets."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
migration = ROOT / "services/decision-service/migrations/020_learning_agronomic_lineage.sql"
persistence = ROOT / "services/decision-service/persistence.py"
missing = []
if not migration.exists():
    missing.append(str(migration.relative_to(ROOT)))
else:
    text = migration.read_text()
    for token in (
        "enforce_learning_agronomic_lineage",
        "agronomic_context_snapshot_id",
        "vegetation_snapshot_id",
        "field_historical_context_snapshot_id",
        "feature_manifest_hash",
        "ENABLE ROW LEVEL SECURITY",
    ):
        if token not in text:
            missing.append(f"migration token:{token}")
text = persistence.read_text()
for token in (
    'source["agronomic_context_snapshot_id"]',
    'source["vegetation_snapshot_id"]',
    'source["field_historical_context_snapshot_id"]',
    '"agronomic_cohorts": cohort_counts',
):
    if token not in text:
        missing.append(f"persistence token:{token}")
if missing:
    print("AGRONOMIC LEARNING LINEAGE GATE: FAIL")
    print("\n".join(f"- {item}" for item in missing))
    sys.exit(1)
print("AGRONOMIC LEARNING LINEAGE GATE: PASS")
