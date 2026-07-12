#!/usr/bin/env python3
"""Phase C gate: the no-leakage certification surface must stay intact.

Guards the master-plan Phase C exit criterion: the randomized property sweep exists
(leaky compositions rejected with typed future_leakage + zero writes; clean accepted),
the DB row invariants are proven composer-independently, and the fail-closed staging
runner is available.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

checks = {
    "services/decision-service/tests/test_no_leakage_certification.py": [
        "test_randomized_no_leakage_property_sweep",
        "future_leakage",
        "zero_writes",
        "test_database_row_invariants_hold_without_the_composer",
        "history_extends_past_as_of",
    ],
    "scripts/certification/certify_no_leakage.py": [
        "DATABASE_URL is required",
        "test_no_leakage_certification.py",
    ],
    "services/decision-service/agronomic_context/point_in_time.py": [
        "future_leakage",
    ],
    "services/decision-service/migrations/018_ac1_agronomic_context.sql": [
        "observed_at <= available_at",
        "history_to <= as_of_time",
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
    print("NO-LEAKAGE CERTIFICATION GATE: FAIL")
    print("\n".join(missing))
    raise SystemExit(1)
print("NO-LEAKAGE CERTIFICATION GATE: PASS")
