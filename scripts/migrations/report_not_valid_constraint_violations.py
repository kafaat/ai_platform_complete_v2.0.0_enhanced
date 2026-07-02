#!/usr/bin/env python3
"""Report rows that violate the deferred (NOT VALID) CHECK constraints.

Step (2) of the professional "NOT VALID -> VALIDATE" procedure documented in
``docs/runbooks/validate_not_valid_constraints.md``. Migrations v127 / v130 / v132
added CHECK constraints as ``NOT VALID`` so the DDL took no heavy lock on existing
rows; the constraints therefore enforce *new/updated* rows only until an operator
runs ``ALTER TABLE ... VALIDATE CONSTRAINT ...`` (step 4). Before that VALIDATE can
succeed the legacy rows must be clean.

This script does NOT run VALIDATE (that is an operator-driven, monitored step). It
only *reports* how many existing rows would fail each constraint, so cleanup/backfill
can be scoped before validation.

A row violates a CHECK when the check predicate evaluates to FALSE (NULL passes,
matching Postgres CHECK semantics). We therefore count ``WHERE NOT (<predicate>)``,
where ``<predicate>`` is copied verbatim from the migration's ADD CONSTRAINT body.

Usage::

    TEST_DATABASE_URL=postgresql://... python scripts/migrations/report_not_valid_constraint_violations.py

Exit codes:
    0  all tracked constraints clean (or table not yet present -> skipped)
    1  at least one constraint has violating rows
    2  no DSN configured / could not connect (nothing was checked)
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NotValidConstraint:
    """A deferred CHECK constraint and the exact predicate copied from its migration."""

    migration: str
    table: str
    name: str
    # Verbatim CHECK body from the ADD CONSTRAINT ... NOT VALID statement. A row is a
    # violation iff this predicate is FALSE, i.e. matched by ``WHERE NOT (<predicate>)``.
    check_predicate: str
    note: str = ""

    def violation_sql(self) -> str:
        return f"SELECT count(*) FROM {self.table} WHERE NOT ({self.check_predicate})"


# Source of truth for the deferred constraints. Predicates are copied verbatim from:
#   - migrations/v127_evidence_context_hardening.sql   (recommendation_outcomes)
#   - migrations/v130_soil_lab_evidence_hardening.sql  (soil_lab_tests)
#   - migrations/v132_field_state_recompute_provenance.sql (field_state)
CONSTRAINTS: list[NotValidConstraint] = [
    NotValidConstraint(
        migration="v132_field_state_recompute_provenance.sql",
        table="field_state",
        name="chk_field_state_version",
        check_predicate="version >= 1",
        note="monotonic recompute counter must be >= 1",
    ),
    NotValidConstraint(
        migration="v127_evidence_context_hardening.sql",
        table="recommendation_outcomes",
        name="chk_reco_outcomes_tenant_not_null",
        check_predicate="tenant_id IS NOT NULL",
        note="tenant scope required (RLS fail-closed)",
    ),
    NotValidConstraint(
        migration="v127_evidence_context_hardening.sql",
        table="recommendation_outcomes",
        name="chk_reco_outcomes_predicted_yield_nonnegative",
        check_predicate="predicted_yield_t_ha IS NULL OR predicted_yield_t_ha >= 0",
        note="predicted yield (t/ha) cannot be negative",
    ),
    NotValidConstraint(
        migration="v127_evidence_context_hardening.sql",
        table="recommendation_outcomes",
        name="chk_reco_outcomes_actual_yield_nonnegative",
        check_predicate="actual_yield_t_ha IS NULL OR actual_yield_t_ha >= 0",
        note="actual yield (t/ha) cannot be negative",
    ),
    NotValidConstraint(
        migration="v130_soil_lab_evidence_hardening.sql",
        table="soil_lab_tests",
        name="chk_soil_lab_ph_range",
        check_predicate="ph IS NULL OR (ph >= 0 AND ph <= 14)",
        note="pH physically bounded 0..14",
    ),
    NotValidConstraint(
        migration="v130_soil_lab_evidence_hardening.sql",
        table="soil_lab_tests",
        name="chk_soil_lab_nonneg",
        # Verbatim conjunction from v130 (whitespace normalized): a row violates if ANY
        # sub-clause is FALSE. WHERE NOT (...) expresses exactly that.
        check_predicate=(
            "(ec_ds_m IS NULL OR ec_ds_m >= 0) AND "
            "(organic_matter_pct IS NULL OR (organic_matter_pct >= 0 AND organic_matter_pct <= 100)) AND "
            "(nitrogen_ppm IS NULL OR nitrogen_ppm >= 0) AND "
            "(phosphorus_ppm IS NULL OR phosphorus_ppm >= 0) AND "
            "(potassium_ppm IS NULL OR potassium_ppm >= 0) AND "
            "(sar IS NULL OR sar >= 0) AND "
            "(calcium_meq_l IS NULL OR calcium_meq_l >= 0) AND "
            "(magnesium_meq_l IS NULL OR magnesium_meq_l >= 0) AND "
            "(sodium_meq_l IS NULL OR sodium_meq_l >= 0) AND "
            "(sample_depth_cm IS NULL OR sample_depth_cm >= 0) AND "
            "(result_version >= 1)"
        ),
        note="analytes/depth non-negative, organic_matter 0..100, result_version >= 1",
    ),
    NotValidConstraint(
        migration="v130_soil_lab_evidence_hardening.sql",
        table="soil_lab_tests",
        name="chk_soil_lab_sample_method",
        check_predicate="sample_method IS NULL OR sample_method IN ('composite', 'grid', 'zone')",
        note="sample_method restricted to composite/grid/zone",
    ),
]


@dataclass
class ConstraintResult:
    constraint: NotValidConstraint
    present: bool = False  # table exists in the connected DB
    violations: int = 0
    error: str = ""
    samples: list = field(default_factory=list)


def dsn() -> str | None:
    """Prefer TEST_DATABASE_URL (CI integration job) then DATABASE_URL."""
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


async def gather_results(url: str) -> list[ConstraintResult]:
    import asyncpg

    conn = await asyncpg.connect(url, statement_cache_size=0)
    results: list[ConstraintResult] = []
    try:
        for c in CONSTRAINTS:
            res = ConstraintResult(constraint=c)
            reg = await conn.fetchval("SELECT to_regclass($1)", c.table)
            if reg is None:
                res.present = False
                results.append(res)
                continue
            res.present = True
            try:
                res.violations = int(await conn.fetchval(c.violation_sql()))
                if res.violations:
                    # A small, bounded sample of offending ctids for triage.
                    rows = await conn.fetch(
                        f"SELECT ctid::text AS ctid FROM {c.table} "
                        f"WHERE NOT ({c.check_predicate}) LIMIT 5"
                    )
                    res.samples = [r["ctid"] for r in rows]
            except Exception as exc:  # noqa: BLE001 - report, do not crash the whole run
                res.error = f"{type(exc).__name__}: {exc}"
            results.append(res)
    finally:
        await conn.close()
    return results


def render(results: list[ConstraintResult]) -> int:
    print("== NOT VALID constraint violation report ==")
    total_violations = 0
    errors = 0
    for res in results:
        c = res.constraint
        header = f"[{c.migration}] {c.table}.{c.name}"
        if not res.present:
            print(f"  SKIP  {header} -- table not present (migration not applied here)")
            continue
        if res.error:
            errors += 1
            print(f"  ERROR {header} -- {res.error}")
            continue
        if res.violations:
            total_violations += res.violations
            sample = f" (sample ctids: {', '.join(res.samples)})" if res.samples else ""
            print(f"  FAIL  {header} -- {res.violations} violating row(s){sample}")
            print(f"        predicate: {c.check_predicate}")
        else:
            print(f"  OK    {header} -- 0 violations")
    print(
        f"-- totals: {total_violations} violating row(s), {errors} query error(s) "
        f"across {len(results)} tracked constraint(s) --"
    )
    if errors:
        return 1
    return 1 if total_violations else 0


def main() -> int:
    url = dsn()
    if not url:
        print(
            "no database configured: set TEST_DATABASE_URL or DATABASE_URL. Nothing was checked.",
            file=sys.stderr,
        )
        return 2
    try:
        results = asyncio.run(gather_results(url))
    except ModuleNotFoundError as exc:
        print(f"asyncpg not installed: {exc}. Nothing was checked.", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - connection failures are a no-DB case
        print(
            f"could not connect ({type(exc).__name__}: {exc}). Nothing was checked.",
            file=sys.stderr,
        )
        return 2
    return render(results)


if __name__ == "__main__":
    raise SystemExit(main())
