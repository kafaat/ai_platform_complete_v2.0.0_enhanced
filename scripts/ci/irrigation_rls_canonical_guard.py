#!/usr/bin/env python3
"""Guard: the V21 irrigation migrations (v168–v181) must use canonical, fail-closed RLS.

Forensic audit (2026-07-14) found three defects in the irrigation program as first landed:
  F-01  v168 tenant policy had a fail-OPEN WITH CHECK: `NULLIF(current_setting(...),'') IS NULL
        OR …` let a session with no app.current_tenant INSERT any tenant_id (cross-tenant write
        injection), even under FORCE RLS.
  F-02  v169/v178–v181 read `app.current_tenant_id`, a key the PLATFORM never sets (it sets
        `app.current_tenant` — 56 call sites + the _set_tenant helper). Those tables' RLS was
        effectively dead for the platform (fail-closed to nobody, or reliant on BYPASSRLS).
  F-08  v178–v181 used CREATE POLICY with no DROP POLICY IF EXISTS → migration re-run failed.

This guard pins the fix so the patterns cannot regress in the irrigation set. It is scoped to
these files ONLY — the fail-open idiom and `app.current_tenant_id` also appear in legacy
platform migrations (a separate, larger pre-existing posture) and in soil-service-owned
migrations (which legitimately pair with soil-service's own session key); those are out of
scope here and must not be swept in.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "migrations"

IRRIGATION = [
    "v168_irrigation_engineering_foundation",
    "v169_canonical_root_zone_hydraulic_profile",
    "v170_water_source_well_digital_twin",
    "v171_pump_hydraulic_network_capability",
    "v172_irrigation_machine_capability",
    "v173_sprinkler_runoff_capability",
    "v174_energy_agricultural_microgrid_capability",
    "v175_unified_irrigation_capability_graph",
    "v176_controller_edge_adapter_framework",
    "v177_irrigation_commissioning_certification",
    "v178_canonical_as_applied_irrigation_truth",
    "v179_hourly_energy_aware_irrigation_mpc",
    "v180_governed_vri_prescription",
    "v181_irrigation_closed_loop_learning_production_certification",
]

# fail-open idiom: a tenant current_setting compared IS NULL joined by OR inside a policy.
_FAIL_OPEN = re.compile(r"current_setting\([^)]*app\.current_tenant[^)]*\)[^;]*?IS NULL\s+OR", re.I)
_CREATE_POLICY = re.compile(r"CREATE POLICY", re.I)
_DROP_POLICY = re.compile(r"DROP POLICY IF EXISTS", re.I)


def main() -> int:
    errors: list[str] = []
    for name in IRRIGATION:
        p = MIG / f"{name}.sql"
        if not p.exists():
            errors.append(f"{name}.sql: MISSING")
            continue
        sql = p.read_text(encoding="utf-8")

        # F-02: canonical key only.
        if "app.current_tenant_id" in sql:
            errors.append(
                f"{name}.sql: uses non-canonical 'app.current_tenant_id' — the platform sets "
                "'app.current_tenant'. Use the canonical key."
            )

        # F-01: no fail-open WITH CHECK escape.
        if _FAIL_OPEN.search(sql):
            errors.append(
                f"{name}.sql: fail-OPEN RLS ('… IS NULL OR …') lets an unset tenant context "
                "write any tenant_id. Use fail-closed: tenant_id = NULLIF(current_setting(...), '')."
            )

        # F-08: every CREATE POLICY must be preceded by an idempotent DROP.
        n_create = len(_CREATE_POLICY.findall(sql))
        n_drop = len(_DROP_POLICY.findall(sql))
        if n_create and n_drop < n_create:
            errors.append(
                f"{name}.sql: {n_create} CREATE POLICY but only {n_drop} DROP POLICY IF EXISTS "
                "— migration re-run will fail (not idempotent)."
            )

    if errors:
        print("irrigation RLS canonical guard: FAIL")
        for e in errors:
            print("  - " + e)
        return 1
    print(f"irrigation RLS canonical guard: PASS ({len(IRRIGATION)} migrations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
