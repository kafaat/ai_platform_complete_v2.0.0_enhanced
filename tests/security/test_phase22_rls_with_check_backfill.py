import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_rls_write_policy_gate_passes():
    result = subprocess.run(
        [sys.executable, "scripts/security/validate_rls_write_policies.py", "--root", str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_v122_backfill_is_defensive_and_idempotent():
    sql = (ROOT / "migrations/v122_rls_with_check_session_unification.sql").read_text()
    assert "CREATE OR REPLACE FUNCTION public.sahool_effective_tenant_id" in sql
    assert "COALESCE" in sql and "app.current_tenant" in sql and "app.tenant_id" in sql
    assert "pg_policies" in sql and "with_check IS NULL" in sql
    assert "ALTER POLICY" in sql and "WITH CHECK" in sql
    assert "RAISE EXCEPTION" in sql


def test_phase_runtime_sets_both_tenant_session_variables():
    for rel in [
        "services/sahool-platform/api/phase_runtime_store.py",
        "services/sahool-platform/api/phase_runtime_workers.py",
    ]:
        text = (ROOT / rel).read_text()
        assert "set_config('app.current_tenant'" in text
        assert "set_config('app.tenant_id'" in text
