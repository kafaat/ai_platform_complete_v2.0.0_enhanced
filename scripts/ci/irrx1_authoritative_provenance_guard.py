#!/usr/bin/env python3
"""Static ratchet for IRR-X1.5 authoritative manual-execution provenance."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = {
    "migration": ROOT / "migrations/v190_irrx1_authoritative_recommendation_provenance_lock.sql",
    "manual router": ROOT / "services/sahool-platform/api/routers/irrigation_engineering.py",
    "decision BFF": ROOT / "services/sahool-platform/api/routers/decision_review.py",
    "decision SoR": ROOT / "services/decision-service/persistence.py",
}
for label, path in checks.items():
    if not path.exists():
        raise SystemExit(f"IRR-X1.5 guard: missing {label}: {path}")

migration = checks["migration"].read_text()
router = checks["manual router"].read_text()
bff = checks["decision BFF"].read_text()
sor = checks["decision SoR"].read_text()
required = [
    (migration, "irrigation_manual_execution_sources"),
    (migration, "IRRX1_AUTHORITATIVE_PROVENANCE_REQUIRED"),
    (migration, "IRRX1_EXECUTION_SOURCE_MISMATCH"),
    (migration, "FORCE ROW LEVEL SECURITY"),
    (router, "AUTHORITATIVE_MANUAL_IRRIGATION_PLAN_NOT_FOUND"),
    (router, "execution_plan_id"),
    (bff, 'req.operation_type == "manual_irrigation"'),
    (bff, "decision-service omitted authoritative plan digest"),
    (sor, '"plan_digest": row["request_hash"]'),
]
for text, token in required:
    if token not in text:
        raise SystemExit(f"IRR-X1.5 guard: missing token {token!r}")
print("IRR-X1.5 authoritative provenance guard: PASS")
