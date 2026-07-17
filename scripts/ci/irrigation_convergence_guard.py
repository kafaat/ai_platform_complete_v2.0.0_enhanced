#!/usr/bin/env python3
"""Fail CI when IRR work introduces a parallel irrigation system of record.

Sliced adoption (see docs/architecture/ADR-IRR-F01-OWNERSHIP.md):
  * The ADR and machine-readable mapping must exist.
  * No IRR migration (>= v195) may create a prohibited parallel SoR table.
  * No IRR migration (>= v195) may ALTER ... ADD COLUMN on irrigation_water_allocations
    (v170 owns that daily-volume quota ledger; per-field flow entitlement belongs
    on the capacity/target-binding side).
  * When the capacity/reservation slice (v195) is present, it must extend the
    existing hydraulic stores and force tenant RLS — it is verified in place.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
ADR = ROOT / "docs" / "architecture" / "ADR-IRR-F01-OWNERSHIP.md"
MAPPING = ROOT / "docs" / "architecture" / "irrigation_convergence_mapping.yml"
CAPACITY_MIGRATION = "v195_irrigation_topology_capacity_convergence.sql"

FORBIDDEN_TABLES = {
    "irrigation_assets",
    "irrigation_executions",
    "irrigation_execution_evidence",
}
FORBIDDEN_ALTER_ADD = {"irrigation_water_allocations"}
FIRST_CONVERGENCE_VERSION = 195


def _migration_version(path: Path) -> int | None:
    match = re.match(r"v(\d+)", path.name)
    return int(match.group(1)) if match else None


def main() -> int:
    errors: list[str] = []

    # 1) Ownership contract artifacts must be present.
    for required in (ADR, MAPPING):
        if not required.exists():
            errors.append(
                f"missing required IRR convergence artifact: {required.relative_to(ROOT)}"
            )

    create_re = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z_][\w]*)", re.I
    )
    alter_add_re = re.compile(
        r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?([a-zA-Z_][\w]*)[^;]*?\bADD\b",
        re.I | re.S,
    )

    # 2) Scan every convergence-era migration for prohibited parallel SoRs and ALTERs.
    for path in sorted(MIGRATIONS.glob("v*.sql")):
        version = _migration_version(path)
        if version is None or version < FIRST_CONVERGENCE_VERSION:
            continue  # Legacy migrations predate the convergence decision.
        text = path.read_text(encoding="utf-8")
        created = {name.lower() for name in create_re.findall(text)}
        duplicate = sorted(created & FORBIDDEN_TABLES)
        if duplicate:
            errors.append(
                f"{path.name} creates prohibited parallel SoR table(s): {', '.join(duplicate)}"
            )
        altered = {name.lower() for name in alter_add_re.findall(text)}
        forbidden_alter = sorted(altered & FORBIDDEN_ALTER_ADD)
        if forbidden_alter:
            errors.append(
                f"{path.name} ADDs columns to a referenced-only store: {', '.join(forbidden_alter)} "
                f"(v170 owns it; carry per-field flow entitlement on the capacity/target-binding side)"
            )

    # 3) If the capacity/reservation slice has landed, verify it extends in place.
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

    if errors:
        print("IRR convergence guard: FAILED")
        for error in errors:
            print(f" - {error}")
        return 1
    print("IRR convergence guard: LOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
