"""Guard — the deferred (NOT VALID) CHECK constraints (v127/v130/v132).

VALIDATE-prep (v133) delivers the *report* + *guard* halves of the professional
"add NOT VALID -> report -> cleanup -> VALIDATE -> guard" procedure (full runbook:
``docs/runbooks/validate_not_valid_constraints.md``).

Two layers:

- **unit** (fast, no DB): the NOT VALID constraints still exist verbatim in their
  migration SQL (nobody silently drops them), and no *blind* ``VALIDATE CONSTRAINT``
  was slipped into a migration file. Validation is operator-run in a monitored
  window per the runbook, gated on a clean violation report — never auto-run by a
  migration. This layer also asserts the report script is present.
- **integration** (real Postgres, like test_imagery_quality_metadata_v57_5): ZERO
  rows violate any tracked constraint on the migrated test DB, so a future dirty
  seed/schema change fails CI.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
REPORT_SCRIPT = ROOT / "scripts" / "migrations" / "report_not_valid_constraint_violations.py"

_TEST_DB = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)  # CI Integration job sets TEST_DATABASE_URL (not DATABASE_URL)

# (migration file, constraint name, a stable substring of its CHECK body) — the exact
# NOT VALID constraints this slice tracks. Kept independent from the report module so a
# regression in one is caught by the other.
_NOT_VALID = [
    ("v132_field_state_recompute_provenance.sql", "chk_field_state_version", "version >= 1"),
    (
        "v127_evidence_context_hardening.sql",
        "chk_reco_outcomes_tenant_not_null",
        "tenant_id IS NOT NULL",
    ),
    (
        "v127_evidence_context_hardening.sql",
        "chk_reco_outcomes_predicted_yield_nonnegative",
        "predicted_yield_t_ha IS NULL OR predicted_yield_t_ha >= 0",
    ),
    (
        "v127_evidence_context_hardening.sql",
        "chk_reco_outcomes_actual_yield_nonnegative",
        "actual_yield_t_ha IS NULL OR actual_yield_t_ha >= 0",
    ),
    ("v130_soil_lab_evidence_hardening.sql", "chk_soil_lab_ph_range", "ph >= 0 AND ph <= 14"),
    (
        "v130_soil_lab_evidence_hardening.sql",
        "chk_soil_lab_nonneg",
        "organic_matter_pct >= 0 AND organic_matter_pct <= 100",
    ),
    (
        "v130_soil_lab_evidence_hardening.sql",
        "chk_soil_lab_sample_method",
        "sample_method IN ('composite', 'grid', 'zone')",
    ),
]


def _load_report_constraints():
    """Import CONSTRAINTS from the report script (single source of truth for predicates)."""
    spec = importlib.util.spec_from_file_location("_nv_report", REPORT_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass introspection needs the module registered
    spec.loader.exec_module(mod)
    return mod.CONSTRAINTS


# ── unit: static guards (no DB) ──────────────────────────────────────────────


@pytest.mark.unit
def test_report_script_present():
    assert REPORT_SCRIPT.exists(), "violation-report script missing — VALIDATE-prep incomplete"


@pytest.mark.unit
def test_not_valid_constraints_still_declared():
    for filename, conname, body in _NOT_VALID:
        sql = (MIGRATIONS / filename).read_text(encoding="utf-8")
        assert conname in sql, f"{conname} dropped from {filename}"
        assert body in sql, f"CHECK body '{body}' changed/removed in {filename} ({conname})"
        # It must still be deferred (NOT VALID) — the migration must not be turned into a
        # locking, blind validation.
        assert "NOT VALID" in sql, f"{filename} no longer declares any NOT VALID constraint"
        assert f"DROP CONSTRAINT IF EXISTS {conname}" not in sql, f"{conname} dropped in {filename}"


def _strip_sql_line_comments(text: str) -> str:
    """Drop ``--`` line comments so a documented VALIDATE mention isn't flagged as a run.

    (v47_schema_integrity.sql legitimately *mentions* VALIDATE CONSTRAINT in comments.)
    """
    out = []
    for line in text.splitlines():
        idx = line.find("--")
        out.append(line if idx == -1 else line[:idx])
    return "\n".join(out)


@pytest.mark.unit
def test_no_blind_validate_constraint_in_migrations():
    """No migration may execute VALIDATE CONSTRAINT (comments are fine).

    Step 4 (``ALTER TABLE ... VALIDATE CONSTRAINT ...``) is operator-run in a monitored
    window, gated on a clean report from report_not_valid_constraint_violations.py — it
    is NOT a migration (a blind VALIDATE would fail hard on legacy dirty rows). If this
    guard ever needs to change, add the report script + a clean-report gate first and
    document it in docs/runbooks/validate_not_valid_constraints.md.
    """
    offenders = []
    for sql_file in MIGRATIONS.glob("*.sql"):
        code = _strip_sql_line_comments(sql_file.read_text(encoding="utf-8"))
        if "VALIDATE CONSTRAINT" in code.upper():
            offenders.append(sql_file.name)
    assert not offenders, (
        "blind VALIDATE CONSTRAINT found in migration(s): "
        + ", ".join(sorted(offenders))
        + " — validation is operator-run per docs/runbooks/validate_not_valid_constraints.md, "
        "not a migration."
    )


@pytest.mark.unit
def test_report_module_covers_every_tracked_constraint():
    tracked = {c.name for c in _load_report_constraints()}
    expected = {conname for _, conname, _ in _NOT_VALID}
    assert expected <= tracked, f"report script missing constraints: {expected - tracked}"


# ── integration: clean migrated DB (real Postgres) ───────────────────────────


def _db_available() -> bool:
    try:
        import asyncpg

        async def _ping():
            c = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


@pytest.mark.integration
def test_zero_violations_on_migrated_db():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import asyncpg

    constraints = _load_report_constraints()

    async def _check():
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        failures = []
        try:
            for c in constraints:
                reg = await conn.fetchval("SELECT to_regclass($1)", c.table)
                if reg is None:
                    # Table not applied in this DB — nothing to validate here.
                    continue
                count = int(await conn.fetchval(c.violation_sql()))
                if count:
                    failures.append(f"{c.table}.{c.name}: {count} violating row(s)")
        finally:
            await conn.close()
        assert not failures, "NOT VALID constraint violations on migrated DB: " + "; ".join(
            failures
        )

    asyncio.run(_check())
