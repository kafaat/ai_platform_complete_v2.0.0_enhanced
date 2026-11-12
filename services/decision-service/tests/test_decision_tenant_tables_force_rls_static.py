"""Static guard: every decision table with a tenant_id ends up ENABLE + FORCE + WITH CHECK.

The platform's last migration (migrations/v206_rls_final_hardening.sql) aborts the whole
deploy when ANY public table with a tenant_id column lacks row-level security enabled AND
forced AND an ALL/INSERT/UPDATE policy with a non-null WITH CHECK. The decision tables
share that database, so a new decision migration that creates a tenant table and forgets
its RLS re-breaks every platform deploy (32 tables did until 037).

This test replays services/decision-service/migrations/0*.sql in order and computes the
end state per table, so the failure names the table at PR time instead of at deploy time.
It understands the three shapes these migrations use: plain statements, quoted EXECUTE
strings, and DO blocks that loop format('... %I ...', t) over an ARRAY of table names.
The live proof against PostgreSQL is test_force_rls_live_pg.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_IDENT = r"[a-z_][a-z0-9_]*"
_WRITE_CMDS = {"ALL", "INSERT", "UPDATE"}

REPO = Path(__file__).resolve().parents[3]
# Platform tables that 001/032 only declare with CREATE TABLE IF NOT EXISTS (for a
# standalone decision DB). On the shared database the platform MANIFEST creates them first
# and hardens them (v78/v79/v66/v49/v119 and later), and v206 itself asserts them on every
# deploy. Each entry is checked below to really be created by a MANIFEST migration.
_PLATFORM_HARDENED: frozenset[str] = frozenset(
    {
        "decision_record",
        "dispatch_decisions",
        "online_learning_updates",
        "outcome_record",
        "recommendation_outcomes",
    }
)


@dataclass
class _TableState:
    enabled: bool = False
    forced: bool = False
    # policy name -> True when it is an ALL/INSERT/UPDATE policy with an explicit WITH CHECK
    policies: dict[str, bool] = field(default_factory=dict)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _units(sql: str) -> list[str]:
    """Split into DO-blocks (kept whole) and plain statements."""
    units: list[str] = []
    pos = 0
    for m in re.finditer(r"DO\s+\$\$.*?\$\$\s*;", sql, flags=re.S | re.I):
        units.extend(s for s in sql[pos : m.start()].split(";") if s.strip())
        units.append(m.group(0))
        pos = m.end()
    units.extend(s for s in sql[pos:].split(";") if s.strip())
    return units


def _unquote(text: str) -> str:
    return text.replace("''", "'")


def _expand(unit: str) -> list[str]:
    """Turn a unit into concrete statements with literal table names."""
    if not re.match(r"\s*DO\s+\$\$", unit, flags=re.I):
        return [unit]
    statements: list[str] = []
    # EXECUTE 'literal statement'
    for m in re.finditer(r"EXECUTE\s+'((?:[^']|'')*)'", unit, flags=re.I):
        statements.append(_unquote(m.group(1)))
    # format('... %I ...', t) looped over ARRAY['a', 'b']
    arrays = re.findall(r"ARRAY\s*\[(.*?)\]", unit, flags=re.S | re.I)
    names = [n for arr in arrays for n in re.findall(r"'(" + _IDENT + r")'", arr)]
    templates = re.findall(r"format\(\s*'((?:[^']|'')*)'", unit, flags=re.I)
    for template in templates:
        template = _unquote(template)
        if "%I" not in template:
            continue
        for name in names:
            statements.append(template.replace("%I", name, 1).replace("%I", name))
    return statements


def _tenant_tables(sql: str) -> set[str]:
    tables: set[str] = set()
    for m in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(" + _IDENT + r")\s*\((.*?)\n\)\s*;",
        sql,
        flags=re.S | re.I,
    ):
        if re.search(r"(?:^|,|\()\s*tenant_id\s+[a-z]", m.group(2), flags=re.M | re.I):
            tables.add(m.group(1).lower())
    for m in re.finditer(
        r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(" + _IDENT + r")\s+ADD\s+COLUMN\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?tenant_id\b",
        sql,
        flags=re.I,
    ):
        tables.add(m.group(1).lower())
    return tables


def _apply(statement: str, state: dict[str, _TableState]) -> None:
    s = " ".join(statement.split())
    m = re.match(
        r"ALTER TABLE (?:IF EXISTS )?(?:ONLY )?(" + _IDENT + r") "
        r"(ENABLE|DISABLE|FORCE|NO FORCE) ROW LEVEL SECURITY$",
        s,
        flags=re.I,
    )
    if m:
        t, action = m.group(1).lower(), m.group(2).upper()
        st = state.setdefault(t, _TableState())
        if action == "ENABLE":
            st.enabled = True
        elif action == "DISABLE":
            st.enabled = False
        elif action == "FORCE":
            st.forced = True
        else:
            st.forced = False
        return
    m = re.match(
        r"DROP POLICY (?:IF EXISTS )?(" + _IDENT + r") ON (" + _IDENT + r")", s, flags=re.I
    )
    if m:
        state.setdefault(m.group(2).lower(), _TableState()).policies.pop(m.group(1).lower(), None)
        return
    m = re.match(r"CREATE POLICY (" + _IDENT + r") ON (" + _IDENT + r")(.*)$", s, flags=re.I | re.S)
    if m:
        name, table, rest = m.group(1).lower(), m.group(2).lower(), m.group(3)
        cmd = re.search(r"\bFOR (ALL|SELECT|INSERT|UPDATE|DELETE)\b", rest, flags=re.I)
        command = cmd.group(1).upper() if cmd else "ALL"
        has_check = re.search(r"\bWITH\s+CHECK\s*\(", rest, flags=re.I) is not None
        restrictive = re.search(r"\bAS RESTRICTIVE\b", rest, flags=re.I) is not None
        state.setdefault(table, _TableState()).policies[name] = (
            command in _WRITE_CMDS and has_check and not restrictive
        )


def _replay() -> tuple[set[str], dict[str, _TableState]]:
    tenant: set[str] = set()
    state: dict[str, _TableState] = {}
    for path in sorted(MIGRATIONS.glob("0*.sql")):
        sql = _strip_comments(path.read_text(encoding="utf-8"))
        tenant |= _tenant_tables(sql)
        for unit in _units(sql):
            for statement in _expand(unit):
                _apply(statement, state)
    return tenant, state


def test_parser_sees_the_known_tenant_tables():
    """Sanity: the parser is not vacuously green (it finds the tables it must guard)."""
    tenant, _state = _replay()
    for table in (
        "decision_record",
        "decision_outbox_events",
        "decision_reviews",
        "decision_execution_requests",
        "decision_model_runtime_work_claims",
        "decision_runtime_worker_tenants",
        "decision_runtime_worker_tenant_commands",
        "decision_agronomic_context_snapshots",
        "decision_eligibility_assessments",
        "decision_reservation_dispatch_inbox",
    ):
        assert table in tenant, table
    assert len(tenant) >= 35


def test_every_decision_tenant_table_is_enabled_forced_and_write_checked():
    tenant, state = _replay()
    offenders = []
    for table in sorted(tenant - _PLATFORM_HARDENED):
        st = state.get(table, _TableState())
        missing = [
            label
            for label, ok in (
                ("ENABLE", st.enabled),
                ("FORCE", st.forced),
                ("ALL/INSERT/UPDATE policy WITH CHECK", any(st.policies.values())),
            )
            if not ok
        ]
        if missing:
            offenders.append(f"{table}: missing {', '.join(missing)}")
    assert not offenders, (
        "decision tables with tenant_id that would trip the platform v206 catalog "
        "assertion (add ENABLE + FORCE + a fail-closed WITH CHECK policy in a new "
        "decision migration):\n" + "\n".join(offenders)
    )


def test_worker_tables_keep_writes_tenant_bound():
    """The worker read policy must never grant writes: it is FOR SELECT only."""
    sql = (MIGRATIONS / "037_force_rls_remaining_tenant_tables.sql").read_text(encoding="utf-8")
    flat = " ".join(_strip_comments(sql).split())
    for table in ("decision_runtime_worker_tenants", "decision_runtime_worker_tenant_commands"):
        read = re.search(rf"CREATE POLICY {table}_worker_read ON {table} (.*?);", flat, flags=re.I)
        assert read, table
        assert read.group(1).upper().startswith("FOR SELECT USING ("), read.group(1)
        assert "WITH CHECK" not in read.group(1).upper()
        assert "current_setting('app.current_worker', true)" in read.group(1)
        tenant = re.search(
            rf"CREATE POLICY {table}_tenant_isolation ON {table} (.*?);", flat, flags=re.I
        )
        assert tenant, table
        assert "app.current_worker" not in tenant.group(1)
        assert "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant'" in (
            tenant.group(1)
        )


def test_037_is_rerunnable():
    """Re-applied on every deploy: every CREATE POLICY is preceded by its DROP IF EXISTS."""
    sql = _strip_comments(
        (MIGRATIONS / "037_force_rls_remaining_tenant_tables.sql").read_text(encoding="utf-8")
    )
    flat = " ".join(sql.split())
    created = re.findall(r"CREATE POLICY (" + _IDENT + r") ON (" + _IDENT + r")", flat)
    assert len(created) >= 28
    for name, table in created:
        drop = f"DROP POLICY IF EXISTS {name} ON {table};"
        assert drop in flat and flat.index(drop) < flat.index(f"CREATE POLICY {name} ON {table}")


def test_platform_allowlist_is_really_platform_owned():
    manifest = (REPO / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    files = [
        line.strip()
        for line in manifest.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    platform_sql = "\n".join(
        (REPO / "migrations" / name).read_text(encoding="utf-8") for name in files
    )
    for table in sorted(_PLATFORM_HARDENED):
        assert re.search(
            rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?{table}\b",
            platform_sql,
            flags=re.I,
        ), f"{table} is allowlisted as platform-hardened but no MANIFEST migration creates it"
