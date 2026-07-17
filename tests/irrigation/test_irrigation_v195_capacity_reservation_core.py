"""IRR-F01 Phase 2 — v195 capacity/reservation core migration contract (static).

Locks the sliced shape: exactly the three capacity/reservation tables, extending
the existing v171 hydraulic stores, fail-closed tenant RLS, no parallel SoR, no
topology/closure tables, no water-allocation ALTER, and a reservation lifecycle
that carries no execution/dispatch state.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "v195_irrigation_capacity_reservation_core.sql"

CORE_TABLES = (
    "hydraulic_capacity_evaluations",
    "irrigation_resource_reservations",
    "irrigation_resource_reservation_events",
)


def test_v195_registered_in_both_runners() -> None:
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    runner = (ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert MIGRATION.name in manifest
    assert MIGRATION.name in runner


def test_v195_creates_only_the_three_core_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for table in CORE_TABLES:
        assert f"create table if not exists {table}" in sql
    # No parallel SoR, no topology/closure, no target binding in this slice.
    for forbidden in (
        "create table if not exists irrigation_assets",
        "create table if not exists irrigation_executions",
        "create table if not exists irrigation_execution_evidence",
        "irrigation_physical_graph_versions",
        "irrigation_physical_path_closure",
        "irrigation_target_bindings",
    ):
        assert forbidden not in sql, f"v195 must not contain {forbidden!r}"
    # v170's quota ledger must not be altered here.
    assert "alter table irrigation_water_allocations" not in sql


def test_v195_extends_existing_hydraulic_stores() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "REFERENCES irrigation_projects(id, tenant_id)" in sql
    # Tenant-scoped capability FK: an evaluation cannot reference another tenant's capability.
    assert (
        "REFERENCES canonical_hydraulic_capabilities(capability_id, tenant_id)" in sql
    )
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_hydraulic_capability_tenant" in sql
    assert "REFERENCES irrigation_hydraulic_nodes(id, tenant_id)" in sql


def test_v195_reservation_events_are_hardened() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    # Deterministic idempotent replay even when causation_id is NULL.
    assert "UNIQUE NULLS NOT DISTINCT (tenant_id, reservation_id, event_type, causation_id)" in sql
    # DB-enforced append-only audit log.
    assert "BEFORE UPDATE OR DELETE ON irrigation_resource_reservation_events" in sql
    assert "is append-only" in sql


def test_v195_forces_tenant_rls_on_all_three_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in CORE_TABLES:
        assert f"'{table}'" in sql
    assert sql.count("FORCE ROW LEVEL SECURITY") >= 1
    assert (
        "WITH CHECK (tenant_id::TEXT = NULLIF(current_setting(''app.current_tenant'', true), ''''))"
        in sql
    )


def test_v195_reservation_lifecycle_has_no_execution_or_dispatch_state() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    # The reservation state domain is reserved/active/released/expired/cancelled only.
    assert "check (state in ('reserved', 'active', 'released', 'expired', 'cancelled'))" in sql
    for leaked in ("'dispatched'", "'acknowledged'", "'started'", "'completed'"):
        assert leaked not in sql, (
            f"reservation must not carry {leaked} (execution/dispatch lineage)"
        )
