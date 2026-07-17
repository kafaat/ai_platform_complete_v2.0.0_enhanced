#!/usr/bin/env python3
"""Fail CI when IRR work introduces a parallel irrigation system of record.

Sliced adoption (see docs/architecture/ADR-IRR-F01-OWNERSHIP.md). For any
migration >= v195 the guard forbids:

  * new parallel execution SoRs (irrigation_assets / irrigation_executions /
    irrigation_execution_evidence);
  * a new canonical hydraulic-capability SoR competing with v171/v175;
  * topology-version / path-closure tables (deferred — need a superseding ADR);
  * turning v170's daily-volume quota ledger (irrigation_water_allocations) into
    a per-field flow/priority allocation SoR by ADD-ing entitlement columns.
    A benign ADD (e.g. a comment/audit column) is allowed — only flow/priority/
    per-field-target entitlement columns are rejected.

It also enforces the dispatch-semantics contract: the pure reservation kernel
must emit a `dispatch_request` and must NOT mark anything `dispatched` (physical
dispatch is confirmed only by the existing actuator receipt path — an outbox
write is not a dispatch).

When the capacity/reservation slice (v195) lands, the guard verifies it extends
the existing hydraulic stores and forces tenant RLS.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
ADR = ROOT / "docs" / "architecture" / "ADR-IRR-F01-OWNERSHIP.md"
MAPPING = ROOT / "docs" / "architecture" / "irrigation_convergence_mapping.yml"
KERNEL = ROOT / "services" / "sahool-platform" / "api" / "irrigation_capacity_reservation.py"
CAPACITY_MIGRATION = "v195_irrigation_capacity_reservation_core.sql"
FIRST_CONVERGENCE_VERSION = 195

# Prohibited new parallel system-of-record tables.
FORBIDDEN_TABLES = {
    "irrigation_assets",
    "irrigation_executions",
    "irrigation_execution_evidence",
}
# A new create matching any of these competes with an existing canonical store
# (v171 canonical_hydraulic_capabilities / v175 capability graph) — forbidden.
FORBIDDEN_CAPABILITY_SOR = (
    "canonical_hydraulic_capabilit",
    "canonical_irrigation_capability_graph",
    "irrigation_capability_graph",
)
# Deferred topology-versioning / closure tables — need a superseding ADR.
FORBIDDEN_TOPOLOGY_TABLES = {
    "irrigation_physical_graph_versions",
    "irrigation_physical_graph_node_memberships",
    "irrigation_physical_graph_segment_memberships",
    "irrigation_physical_path_closure",
}
# v170's quota ledger must not gain per-field flow/priority entitlement columns.
QUOTA_LEDGER = "irrigation_water_allocations"
FORBIDDEN_ADD_COLUMNS = {
    "allocated_flow_m3h",
    "allocated_flow_lps",
    "priority",
    "allocation_basis",
    "allocation_share_pct",
    "farm_id",
    "field_id",
}


def _migration_version(path: Path) -> int | None:
    match = re.match(r"v(\d+)", path.name)
    return int(match.group(1)) if match else None


def _created_tables(text: str) -> set[str]:
    create_re = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z_][\w]*)", re.I
    )
    return {name.lower() for name in create_re.findall(text)}


def _quota_ledger_added_columns(text: str) -> set[str]:
    """Columns ADD-ed to irrigation_water_allocations in this migration."""
    added: set[str] = set()
    alter_re = re.compile(
        r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?" + QUOTA_LEDGER + r"\b(.*?);",
        re.I | re.S,
    )
    add_col_re = re.compile(r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][\w]*)", re.I)
    for body in alter_re.findall(text):
        added.update(name.lower() for name in add_col_re.findall(body))
    return added


def main() -> int:
    errors: list[str] = []

    # 1) Ownership contract artifacts must be present.
    for required in (ADR, MAPPING):
        if not required.exists():
            errors.append(
                f"missing required IRR convergence artifact: {required.relative_to(ROOT)}"
            )

    # 2) Scan every convergence-era migration.
    for path in sorted(MIGRATIONS.glob("v*.sql")):
        version = _migration_version(path)
        if version is None or version < FIRST_CONVERGENCE_VERSION:
            continue  # Legacy migrations predate the convergence decision.
        text = path.read_text(encoding="utf-8")
        created = _created_tables(text)

        duplicate = sorted(created & FORBIDDEN_TABLES)
        if duplicate:
            errors.append(
                f"{path.name} creates prohibited parallel SoR table(s): {', '.join(duplicate)}"
            )

        capability = sorted(
            name for name in created if any(name.startswith(p) for p in FORBIDDEN_CAPABILITY_SOR)
        )
        if capability:
            errors.append(
                f"{path.name} creates a competing hydraulic-capability SoR: {', '.join(capability)} "
                f"(v171/v175 own canonical capability — reuse, do not duplicate)"
            )

        topology = sorted(created & FORBIDDEN_TOPOLOGY_TABLES)
        if topology:
            errors.append(
                f"{path.name} creates deferred topology-version/closure table(s): {', '.join(topology)} "
                f"(needs a superseding ADR; path is answered by a query over v171)"
            )

        forbidden_add = sorted(_quota_ledger_added_columns(text) & FORBIDDEN_ADD_COLUMNS)
        if forbidden_add:
            errors.append(
                f"{path.name} ADDs flow/priority entitlement column(s) to {QUOTA_LEDGER}: "
                f"{', '.join(forbidden_add)} (v170 owns it as a daily-volume quota ledger; per-field "
                f"flow/priority allocation belongs on the capacity/target-binding side)"
            )

    # 3) Dispatch-semantics contract on the pure kernel: a committed reservation +
    #    outbox record means dispatch_requested, never dispatched.
    if KERNEL.exists():
        kernel_text = KERNEL.read_text(encoding="utf-8")
        if "dispatch_request" not in kernel_text:
            errors.append(f"{KERNEL.name} must express dispatch_request semantics")
        # A real violation is a 'dispatched' state literal, not the word in prose
        # explaining that we deliberately do NOT dispatch here.
        if re.search(r"""['"]dispatched['"]""", kernel_text):
            errors.append(
                f"{KERNEL.name} must not set a 'dispatched' state literal "
                f"(an outbox write is a dispatch REQUEST; the actuator receipt confirms dispatch)"
            )

    # 4) If the capacity/reservation slice has landed, verify it extends in place
    #    and that the reservation lifecycle carries no execution/dispatch states.
    capacity_path = MIGRATIONS / CAPACITY_MIGRATION
    if capacity_path.exists():
        migration = capacity_path.read_text(encoding="utf-8")
        for required_text in (
            "irrigation_hydraulic_nodes",
            "canonical_hydraulic_capabilities",
            "irrigation_resource_reservations",
            "hydraulic_capacity_evaluations",
            "FORCE ROW LEVEL SECURITY",
        ):
            if required_text not in migration:
                errors.append(
                    f"{CAPACITY_MIGRATION} missing convergence contract token: {required_text}"
                )
        reservation_state_block = re.search(
            r"state\s+TEXT[^;]*?CHECK\s*\(\s*state\s+IN\s*\(([^)]*)\)", migration, re.I | re.S
        )
        if reservation_state_block:
            states = reservation_state_block.group(1).lower()
            leaked = sorted(
                s for s in ("dispatched", "acknowledged", "started", "completed") if s in states
            )
            if leaked:
                errors.append(
                    f"{CAPACITY_MIGRATION} reservation state must not carry execution/dispatch "
                    f"state(s): {', '.join(leaked)} (those belong to the execution/dispatch lineage)"
                )

    if errors:
        print("IRR convergence guard: FAILED")
        for error in errors:
            print(f" - {error}")
        return 1
    print("IRR convergence guard: LOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
