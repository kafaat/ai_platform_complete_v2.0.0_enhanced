#!/usr/bin/env python3
"""Static ratchet for IRR-PCERT wiring and DB-authoritative invariants."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = {
    "migrations/v189_irrx1_pcert_manual_execution_db_invariants.sql": [
        "irrigation_manual_executions_legal_state_guard",
        "IRRX1_INVALID_DB_TRANSITION",
        "irrigation_manual_events_tenant_execution_fk",
        "irrigation_manual_reconciliation_tenant_execution_fk",
    ],
    "tests_v9/test_irrx1_pcert_real_postgres.py": [
        "pytest.mark.integration",
        "TEST_DATABASE_URL",
        "IRRX1_INVALID_DB_TRANSITION",
        "ForeignKeyViolationError",
    ],
    "migrations/MANIFEST.txt": ["v189_irrx1_pcert_manual_execution_db_invariants.sql"],
    "scripts_v9/run_migrations.sql": ["v189_irrx1_pcert_manual_execution_db_invariants.sql"],
    ".github/workflows/ci.yml": ["irrx1_pcert_guard.py"],
}
errors: list[str] = []
for rel, needles in required.items():
    path = ROOT / rel
    if not path.exists():
        errors.append(f"missing {rel}")
        continue
    text = path.read_text(encoding="utf-8")
    errors.extend(f"{rel}: missing {needle}" for needle in needles if needle not in text)
if errors:
    raise SystemExit("IRR-PCERT guard FAILED:\n- " + "\n- ".join(errors))
print("IRR-PCERT guard: PASS")
