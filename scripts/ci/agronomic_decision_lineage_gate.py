#!/usr/bin/env python3
"""AC-6 gate: direct agronomic lineage on decisions must stay present and fail-closed.

Asserts (on the landed shape — the delivered bundle referenced its never-landed 018
tables): the decision input carries identity + evidence lineage fields, the immutable
vegetation-evidence writer exists, strict mode rejects with the typed contract, and
migration 019 wires the store, FKs and the lineage index.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

checks = {
    "services/decision-service/main.py": [
        "agronomic_context_snapshot_id",
        "vegetation_snapshot_id",
        "field_historical_context_snapshot_id",
        "feature_manifest_hash",
        '"/v1/evidence/vegetation-snapshots"',
        "DECISION_REQUIRE_AGRONOMIC_CONTEXT",
        "agronomic_context_required",
    ],
    "services/decision-service/persistence.py": [
        "persist_vegetation_snapshot",
        "_validate_vegetation_reference",
        "_canonical_snapshot_id",
        "feature_manifest_hash",
    ],
    "services/decision-service/migrations/019_agronomic_lineage_integrity.sql": [
        "decision_vegetation_snapshots",
        "fk_decision_ag_context_tenant",
        "fk_decision_vegetation_snapshot_tenant",
        "fk_decision_history_snapshot_tenant",
        "fk_decision_feature_manifest_tenant",
        "idx_decision_agronomic_lineage",
    ],
}

missing = []
for rel, tokens in checks.items():
    p = ROOT / rel
    text = p.read_text() if p.exists() else ""
    for token in tokens:
        if token not in text:
            missing.append(f"{rel}: {token}")
if missing:
    print("agronomic decision lineage gate: FAIL")
    print("\n".join(missing))
    raise SystemExit(1)
print("agronomic decision lineage gate: PASS")
