from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "v192_fii_rls_write_fail_closed.sql"


def test_fii_rls_static_ratchet_passes():
    result = subprocess.run(
        [sys.executable, "scripts/ci/fii_rls_write_policy_gate.py", "--root", str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_v192_is_fail_closed_for_both_initial_tables():
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in ("scouting_pins", "prescriptions"):
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
        assert f"CREATE POLICY tenant_isolation ON {table}" in sql
    assert sql.count("WITH CHECK") == 2
    assert "IS NULL\n                OR" not in sql
    assert (
        sql.count("tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')") == 4
    )
