from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "v194_fii_chemical_chain_rls_fail_closed.sql"

TABLES = (
    "recommendations",
    "decision_record",
    "work_orders",
    "actuator_command_dedup",
    "outcome_record",
    "lineage_link",
)


def test_v194_covers_existing_chemical_chain_tables():
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"'{table}'" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert (
        "WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))"
        in sql
    )
    assert "IS NULL" not in sql
    assert "WITH CHECK (TRUE)" not in sql.upper()


def test_v194_is_registered_in_both_migration_runners():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    runner = (ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert "v194_fii_chemical_chain_rls_fail_closed.sql" in manifest
    assert "v194_fii_chemical_chain_rls_fail_closed.sql" in runner
