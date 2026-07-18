"""IRR-F01 — v196 target-binding migration contract (static)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "v196_irrigation_target_binding.sql"


def test_v196_registered_in_both_runners() -> None:
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    runner = (ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert MIGRATION.name in manifest
    assert MIGRATION.name in runner


def test_v196_binds_to_existing_terminal_node_without_new_geometry_sor() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "create table if not exists irrigation_target_bindings" in sql.lower()
    assert "REFERENCES irrigation_hydraulic_nodes(id, tenant_id)" in sql
    assert "REFERENCES irrigation_projects(id, tenant_id)" in sql
    assert "target_type" in sql and "management_zone" in sql
    # Version-pinned + at most one open binding per target.
    assert "target_version_id" in sql
    assert "uq_irrigation_target_binding_current" in sql
    # No deferred graph-version reference in this slice.
    assert "graph_version_id" not in sql


def test_v196_forces_tenant_rls() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert (
        "WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))"
        in sql
    )
