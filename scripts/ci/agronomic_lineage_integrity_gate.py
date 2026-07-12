#!/usr/bin/env python3
"""AC-6.1 gate: tenant-safe agronomic lineage and semantic evidence consistency.

Guards migration 019's DB-level integrity layer: tenant-composite foreign keys (a guessed
or replayed snapshot ID from another tenant can never satisfy a reference), the semantic
field/season validation trigger, tenant RLS on the authoritative tables, and the
persistence-side tenant binding + truly-idempotent canonical snapshot replay.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
migration = (
    ROOT / "services/decision-service/migrations/019_agronomic_lineage_integrity.sql"
).read_text()
persistence = (ROOT / "services/decision-service/persistence.py").read_text()

required = [
    "FOREIGN KEY (tenant_id, agronomic_context_snapshot_id)",
    "FOREIGN KEY (tenant_id, vegetation_snapshot_id)",
    "FOREIGN KEY (tenant_id, field_historical_context_snapshot_id)",
    "FOREIGN KEY (tenant_id, feature_manifest_id)",
    "decision_validate_agronomic_lineage",
    "agronomic context field/season mismatch",
    "vegetation snapshot field/season mismatch",
    "field history snapshot field/season mismatch",
    "feature manifest hash mismatch",
    "ENABLE ROW LEVEL SECURITY",
    "ck_decision_feature_manifest_hash",
]
missing = [item for item in required if item not in migration]

decision_fn = persistence.split("async def persist_decision_record", 1)[1].split(
    "async def persist_dispatch_decision", 1
)[0]
if "set_config('app.current_tenant'" not in decision_fn:
    missing.append("tenant RLS binding in persist_decision_record")
if "lineage_integrity_violation" not in decision_fn:
    missing.append("fail-closed DB-backstop mapping in persist_decision_record")
if "_canonical_snapshot_id" not in persistence or "RETURNING snapshot_id" not in persistence:
    missing.append("canonical idempotent snapshot persistence")
if '"created": canonical == snapshot_id' not in persistence:
    missing.append("replay must report created=False with the canonical snapshot id")

if missing:
    raise SystemExit("AGRONOMIC LINEAGE INTEGRITY GATE: FAIL: " + ", ".join(missing))
print("AGRONOMIC LINEAGE INTEGRITY GATE: PASS")
