from pathlib import Path

root = Path(__file__).resolve().parents[2]
checks = {
    "runtime": root / "services/sahool-platform/api/irrigation_manual_execution.py",
    "migration": root / "migrations/v187_irrx1_manual_execution_lifecycle.sql",
    "tests": root / "tests_v9/test_irrx1_2_manual_execution_lifecycle.py",
}
for name, path in checks.items():
    assert path.exists(), f"missing {name}: {path}"
runtime = checks["runtime"].read_text(encoding="utf-8")
for token in [
    "RECOMMENDED",
    "APPROVED",
    "STARTED",
    "STOPPED",
    "CONFIRMED",
    "VERIFIED",
    "RECONCILED",
    "ledger_eligible",
]:
    assert token in runtime, f"missing lifecycle token {token}"
sql = checks["migration"].read_text(encoding="utf-8")
for token in ["FORCE ROW LEVEL SECURITY", "append-only", "idempotency_key"]:
    assert token in sql, f"missing SQL guard {token}"
print("IRR-X1.2 manual execution guard: PASS")
