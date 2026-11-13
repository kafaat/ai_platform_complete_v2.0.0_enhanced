"""Every literal SQL statement in services/ and shared/ must at least PREPARE on the real schema.

Test doubles accept any SQL, so three classes of defect reached main and failed on every call
on the shared database:

* the same ``$n`` bound to columns of different types (``created_by varchar`` and
  ``verified_by text`` in decision-service outcome verification -> 500 on every call);
* a bound parameter that is never referenced (``$2`` in field-form publication), or one whose
  type Postgres cannot deduce (recommendation outcomes) -> the statement never runs;
* an ``ON CONFLICT`` target with no matching unique constraint.

The first two are rejected at PREPARE (parse analysis). The third is not: Postgres picks the
ON CONFLICT arbiter index in the PLANNER, so a statement whose target matches only a partial
unique index (``ON CONFLICT (tenant_id, user_ref)`` against ``... WHERE user_ref IS NOT NULL``)
prepares cleanly and fails with 42P10 on every execution - notification preferences were never
saved that way. Statements carrying ON CONFLICT are therefore also planned with
``EXPLAIN (GENERIC_PLAN)`` (PostgreSQL 16+; no parameter values, nothing executed). Everything
runs inside one transaction that is rolled back. Decision-service tables
live in the same database in production, so its migrations are applied inside that transaction
first. Other errors (a table owned by a service with its own database) are counted, not failed:
this contract is about the three classes above, which have no legitimate cause.

Runs in "Live PG Proofs" (``SAHOOL_REQUIRE_LIVE_PG=1``: absent database = failure, not skip).
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[1]
DECISION_MIGRATIONS = sorted((ROOT / "services/decision-service/migrations").glob("0*.sql"))
_REQUIRE = os.environ.get("SAHOOL_REQUIRE_LIVE_PG") == "1"

# SQLSTATEs that only ever mean "this statement is wrong", never "this table is elsewhere".
DEFECT_SQLSTATES = {
    "42P08": "inconsistent types deduced for a parameter",
    "42P18": "parameter type cannot be determined",
    "42P10": "ON CONFLICT target has no matching unique constraint",
}
_SQL_START = re.compile(r"(?is)^\s*(with|select|insert|update|delete)\b")
_QUOTED = re.compile(r"'(?:[^']|'')*'")
_ON_CONFLICT = re.compile(r"(?i)\bon\s+conflict\b")


def _statements() -> list[tuple[str, int, str]]:
    out = []
    for base in ("services", "shared"):
        for path in sorted((ROOT / base).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in rel or path.name.startswith("test_"):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            # Fragments of f-strings are incomplete statements; skip them by position.
            fstring_parts = {
                id(part)
                for node in ast.walk(tree)
                if isinstance(node, ast.JoinedStr)
                for part in node.values
            }
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                if id(node) in fstring_parts:
                    continue
                sql = node.value
                # Only complete asyncpg statements: positional $n and no str.format() hole.
                # A brace inside a quoted SQL literal ('{}'::jsonb) is SQL, not a template.
                unquoted = _QUOTED.sub("''", sql)
                if _SQL_START.match(sql) and re.search(r"\$\d", sql) and "{" not in unquoted:
                    out.append((rel, node.lineno, sql))
    return out


def _dsn() -> dict:
    return {
        "host": os.environ.get("SAHOOL_TEST_PGHOST", "/var/run/postgresql"),
        "port": int(os.environ.get("SAHOOL_TEST_PGPORT", "5432")),
        "database": os.environ.get("SAHOOL_TEST_PGDATABASE", "sahool"),
        "user": os.environ.get("SAHOOL_TEST_PGOWNER", "sahool_user"),
        "password": os.environ.get("PGPASSWORD"),
    }


async def _prepare_all(statements):
    import asyncpg

    conn = await asyncpg.connect(**_dsn(), timeout=10)
    defects, other = [], 0
    try:
        # EXPLAIN (GENERIC_PLAN) exists from PostgreSQL 16; on an older server every planned
        # statement would fail into the uncounted bucket and the contract would pass vacuously.
        assert int(await conn.fetchval("SHOW server_version_num")) >= 160000, (
            "the ON CONFLICT generic-plan contract needs PostgreSQL 16+"
        )
        tx = conn.transaction()
        await tx.start()
        try:
            for migration in DECISION_MIGRATIONS:
                await conn.execute(migration.read_text(encoding="utf-8"))
            for rel, line, sql in statements:
                sp = conn.transaction()
                await sp.start()
                try:
                    await conn.prepare(sql)
                    if _ON_CONFLICT.search(sql):
                        # Arbiter inference happens at planning, not at PREPARE.
                        await conn.execute("EXPLAIN (GENERIC_PLAN) " + sql)
                except asyncpg.PostgresError as exc:
                    code = getattr(exc, "sqlstate", "")
                    if code in DEFECT_SQLSTATES:
                        defects.append(f"{rel}:{line} [{code}] {exc}")
                    else:
                        other += 1
                finally:
                    await sp.rollback()
        finally:
            await tx.rollback()
    finally:
        await conn.close()
    return defects, other


def _db_reachable() -> bool:
    try:
        import asyncpg
    except ImportError:
        return False

    async def ping():
        conn = await asyncpg.connect(**_dsn(), timeout=5)
        await conn.close()

    try:
        asyncio.run(ping())
        return True
    except Exception:  # noqa: BLE001 - any failure means "no database here"
        return False


def test_statement_inventory_is_not_empty():
    statements = _statements()
    # A broken extractor would make the contract pass vacuously.
    assert len(statements) > 500, len(statements)
    assert any(rel == "services/decision-service/persistence.py" for rel, _, _ in statements)


def test_every_statement_prepares_without_a_defect_sqlstate():
    if not _db_reachable():
        if _REQUIRE:
            pytest.fail("SAHOOL_REQUIRE_LIVE_PG=1 but the database is unreachable")
        pytest.skip("no live Postgres (set SAHOOL_REQUIRE_LIVE_PG=1 to make this a failure)")
    statements = _statements()
    defects, other = asyncio.run(_prepare_all(statements))
    assert not defects, "statements the server rejects at PREPARE:\n" + "\n".join(defects)
    # Most statements must prepare; a collapse here means the schema was not migrated.
    assert other < len(statements) // 4, (other, len(statements))
