"""Cutover-time DB-level revocation of platform write access on the decision SoR tables.

This is the **complementary DB-level enforcement** for the app-layer guard in
``services/sahool-platform/api/decision_sor_mode.py::assert_platform_may_write_decision_sor``.
The app guard fails closed *in Python* once the platform is demoted; this tool additionally
strips ``INSERT/UPDATE/DELETE`` from the platform role *at the database*, so a platform write
is denied even if the Python guard is bypassed (a stray code path, a psql session, a rollback
of the app image). ``SELECT`` is intentionally kept — after demotion the platform stays a
read-side BFF / compatibility facade.

Scope — SAME-DB topology only
-----------------------------
The cutover runbook supports two topologies (see
``docs/runbooks/DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md``). This REVOKE is meaningful only when
the platform app role and decision-service share ONE Postgres and the SoR tables are physically
the platform's tables. In the split-DB topology the platform has no grant on the decision
database at all, so the REVOKE is a no-op there and simply need not be run.

Table set
---------
Exactly the FIVE platform-owned SoR tables (``docs/architecture/db_ownership.yml`` —
owner ``sahool-platform``, mirror ``decision-service``, status ``interim-bridge``). The sixth
canonical SoR table, ``decision_outbox_events``, is decision-service-owned (created by
``services/decision-service/migrations/001_decision_sor.sql``) — the platform never writes it,
so it is deliberately excluded from the platform REVOKE.

Reversibility
-------------
``--revoke`` and ``--grant`` are exact inverses over the same table/privilege set, so a rollback
(``rollback.py`` step) restores the pre-cutover grants. This tool is NOT a migration: it lives
outside ``services/decision-service/migrations/`` precisely because those run on *every* schema
deploy (all ``CREATE TABLE IF NOT EXISTS``, applied pre-cutover). A REVOKE there would strip
platform writes *before* demotion and break the pre-cutover platform-as-SoR contract.

Fail-closed gates (mutation only; ``--check`` is always read-only)
------------------------------------------------------------------
``--revoke`` requires BOTH ``DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true`` (the same final
gate that flips ``platform_writes_required`` off in ``decision_sor_mode`` / ``can_demote_platform``
in ``cutover.py``) AND ``DECISION_SOR_ALLOW_PLATFORM_REVOKE=true``.
``--grant`` (rollback) requires ``DECISION_SERVICE_ROLLBACK_APPROVED=true`` (the same env
``rollback.py`` uses) AND ``DECISION_SOR_ALLOW_PLATFORM_REVOKE=true``.

Usage:
    DECISION_SOR_ADMIN_DATABASE_URL=postgres://owner...  \
    DECISION_SOR_PLATFORM_ROLE=sahool_app                \
    python services/decision-service/platform_sor_revoke.py --check

Required env:
    DECISION_SOR_ADMIN_DATABASE_URL   # a role that OWNS the tables (or superuser) — able to REVOKE
    DECISION_SOR_PLATFORM_ROLE        # the platform app role to revoke writes from (e.g. sahool_app)

Optional env:
    DECISION_SOR_TABLE_SCHEMA=public  # schema holding the SoR tables (default: public)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from typing import Any

# The FIVE platform-owned SoR tables (decision_outbox_events is decision-service-owned — excluded).
# Kept in lockstep with sahool-platform `decision_sor_mode.DECISION_SOR_TABLES` minus the outbox.
PLATFORM_SOR_TABLES: tuple[str, ...] = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
)

# Writes are revoked; SELECT is deliberately retained (platform stays a read-side facade).
WRITE_PRIVILEGES: tuple[str, ...] = ("INSERT", "UPDATE", "DELETE")
RETAINED_PRIVILEGE = "SELECT"

_TRUTHY = {"1", "true", "yes", "on"}
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

# Fail-closed mutation gates.
CUTOVER_APPROVED_ENV = "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED"
ROLLBACK_APPROVED_ENV = "DECISION_SERVICE_ROLLBACK_APPROVED"
ALLOW_REVOKE_ENV = "DECISION_SOR_ALLOW_PLATFORM_REVOKE"


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


def _validate_identifier(name: str, *, kind: str) -> str:
    """Reject anything that is not a plain SQL identifier.

    Role and schema names cannot be passed as bound parameters to REVOKE/GRANT, so they are
    embedded into the statement text. This strict allowlist (letters/digits/underscore/$, not
    starting with a digit) makes that embedding injection-safe; the value is additionally
    double-quoted at use.
    """
    name = (name or "").strip()
    if not _IDENT_RE.match(name):
        raise SystemExit(f"invalid {kind} identifier: {name!r} (must match {_IDENT_RE.pattern})")
    return name


def admin_database_url() -> str:
    url = os.getenv("DECISION_SOR_ADMIN_DATABASE_URL", "").strip()
    if not url:
        raise SystemExit(
            "DECISION_SOR_ADMIN_DATABASE_URL is required (a role that OWNS the SoR tables "
            "or a superuser — able to REVOKE/GRANT). Never the platform app role itself."
        )
    return url


def platform_role() -> str:
    role = os.getenv("DECISION_SOR_PLATFORM_ROLE", "").strip()
    if not role:
        raise SystemExit(
            "DECISION_SOR_PLATFORM_ROLE is required (the platform app role to revoke writes "
            "from, e.g. sahool_app). It is operator-supplied — never hardcoded."
        )
    return _validate_identifier(role, kind="role")


def table_schema() -> str:
    return _validate_identifier(
        os.getenv("DECISION_SOR_TABLE_SCHEMA", "public").strip() or "public", kind="schema"
    )


def _qualified(schema: str, table: str) -> str:
    # `table` values come from the PLATFORM_SOR_TABLES constant; schema is validated above.
    return f'"{schema}"."{table}"'


async def privilege_state(
    conn: Any, role: str, *, schema: str = "public", tables: tuple[str, ...] = PLATFORM_SOR_TABLES
) -> dict[str, dict[str, bool]]:
    """Return {table: {INSERT/UPDATE/DELETE/SELECT: bool}} for ``role`` — read-only."""
    state: dict[str, dict[str, bool]] = {}
    for table in tables:
        qualified = f"{schema}.{table}"
        privs: dict[str, bool] = {}
        for priv in (*WRITE_PRIVILEGES, RETAINED_PRIVILEGE):
            privs[priv] = bool(
                await conn.fetchval("SELECT has_table_privilege($1, $2, $3)", role, qualified, priv)
            )
        state[table] = privs
    return state


def privilege_closure_findings(state: dict[str, dict[str, bool]], *, action: str) -> list[str]:
    """Validate effective DB privileges, including inherited/PUBLIC grants.

    ``has_table_privilege`` is intentionally used upstream instead of reading only direct GRANT
    rows. A direct REVOKE that leaves an inherited write privilege is not a successful cutover.
    """
    findings: list[str] = []
    for table in PLATFORM_SOR_TABLES:
        privs = state.get(table) or {}
        if action == "revoke":
            for privilege in WRITE_PRIVILEGES:
                if privs.get(privilege) is not False:
                    findings.append(f"{table}:{privilege}:effective_write_still_allowed")
            if privs.get(RETAINED_PRIVILEGE) is not True:
                findings.append(f"{table}:{RETAINED_PRIVILEGE}:read_facade_privilege_missing")
        elif action == "grant":
            for privilege in (*WRITE_PRIVILEGES, RETAINED_PRIVILEGE):
                if privs.get(privilege) is not True:
                    findings.append(f"{table}:{privilege}:rollback_privilege_missing")
    return findings


class PrivilegeClosureError(RuntimeError):
    pass


async def revoke_platform_writes(
    conn: Any, role: str, *, schema: str = "public", tables: tuple[str, ...] = PLATFORM_SOR_TABLES
) -> None:
    """REVOKE INSERT/UPDATE/DELETE (never SELECT) on the platform SoR tables from ``role``."""
    role = _validate_identifier(role, kind="role")
    schema = _validate_identifier(schema, kind="schema")
    privs = ", ".join(WRITE_PRIVILEGES)
    async with conn.transaction():
        for table in tables:
            await conn.execute(f'REVOKE {privs} ON {_qualified(schema, table)} FROM "{role}"')


async def grant_platform_writes(
    conn: Any, role: str, *, schema: str = "public", tables: tuple[str, ...] = PLATFORM_SOR_TABLES
) -> None:
    """Exact inverse of :func:`revoke_platform_writes` — restores the pre-cutover write grants."""
    role = _validate_identifier(role, kind="role")
    schema = _validate_identifier(schema, kind="schema")
    privs = ", ".join(WRITE_PRIVILEGES)
    async with conn.transaction():
        for table in tables:
            await conn.execute(f'GRANT {privs} ON {_qualified(schema, table)} TO "{role}"')


async def _connect(url: str):
    try:
        import asyncpg  # type: ignore
    except ImportError as exc:  # pragma: no cover - deploy/runtime dependency
        raise SystemExit("asyncpg is required for the platform SoR revoke tool") from exc
    return await asyncpg.connect(url, statement_cache_size=0)


async def _run(action: str) -> dict[str, Any]:
    role = platform_role()
    schema = table_schema()
    conn = await _connect(admin_database_url())
    try:
        if action == "check":
            before = await privilege_state(conn, role, schema=schema)
            return {
                "action": action,
                "role": role,
                "schema": schema,
                "tables": list(PLATFORM_SOR_TABLES),
                "revoked_privileges": list(WRITE_PRIVILEGES),
                "retained_privilege": RETAINED_PRIVILEGE,
                "before": before,
                "after": before,
                "closure_verified": None,
                "closure_findings": [],
            }

        # Mutation + effective postcondition are ONE transaction. If an inherited/PUBLIC grant
        # leaves writes enabled (or rollback fails to restore them), raising here rolls back the
        # direct GRANT/REVOKE instead of leaving a half-certified privilege state behind.
        async with conn.transaction():
            before = await privilege_state(conn, role, schema=schema)
            if action == "revoke":
                if not (_truthy(CUTOVER_APPROVED_ENV) and _truthy(ALLOW_REVOKE_ENV)):
                    raise SystemExit(
                        f"refusing to REVOKE: require {CUTOVER_APPROVED_ENV}=true and "
                        f"{ALLOW_REVOKE_ENV}=true (cutover-approved, fail-closed)"
                    )
                await revoke_platform_writes(conn, role, schema=schema)
            elif action == "grant":
                if not (_truthy(ROLLBACK_APPROVED_ENV) and _truthy(ALLOW_REVOKE_ENV)):
                    raise SystemExit(
                        f"refusing to GRANT (rollback): require {ROLLBACK_APPROVED_ENV}=true and "
                        f"{ALLOW_REVOKE_ENV}=true"
                    )
                await grant_platform_writes(conn, role, schema=schema)
            after = await privilege_state(conn, role, schema=schema)
            closure = privilege_closure_findings(after, action=action)
            if closure:
                raise PrivilegeClosureError(";".join(closure))
            return {
                "action": action,
                "role": role,
                "schema": schema,
                "tables": list(PLATFORM_SOR_TABLES),
                "revoked_privileges": list(WRITE_PRIVILEGES),
                "retained_privilege": RETAINED_PRIVILEGE,
                "before": before,
                "after": after,
                "closure_verified": True,
                "closure_findings": [],
            }
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cutover-time DB REVOKE/GRANT of platform writes on the decision SoR tables"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check", action="store_true", help="Print current privilege state (read-only)"
    )
    group.add_argument(
        "--revoke", action="store_true", help="Revoke platform writes (cutover-gated)"
    )
    group.add_argument(
        "--grant", action="store_true", help="Restore platform writes (rollback-gated)"
    )
    args = parser.parse_args(argv)
    action = "revoke" if args.revoke else "grant" if args.grant else "check"

    import json

    try:
        result = asyncio.run(_run(action))
    except PrivilegeClosureError as exc:
        print(
            json.dumps(
                {"action": action, "closure_verified": False, "error": str(exc)},
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
