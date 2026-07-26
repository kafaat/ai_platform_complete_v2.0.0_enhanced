"""Read-only PRE-CUTOVER role/privilege certification for the decision-SoR cutover.

The mandatory precursor to any platform-write REVOKE (``platform_sor_revoke.py``). The REVOKE
*assumes* the platform and decision-service connect as DIFFERENT Postgres roles; this tool PROVES
(or disproves) that against the live database — it NEVER runs GRANT/REVOKE, only SELECTs from the
catalogs. If the two connections resolve to the SAME role, a REVOKE would strip writes from both
services, so role separation must be established first.

It emits a live privilege matrix for each supplied connection:
  * current_user / session_user and their role attributes (rolsuper, rolbypassrls, rolcreaterole,
    rolcreatedb, rolcanlogin) — the platform/service roles MUST be NOSUPERUSER + NOBYPASSRLS;
  * the OWNER of each of the five platform-owned SoR tables (owner retains privileges even after a
    REVOKE — so ``sahool_app`` must NOT own them if the goal is to bar it);
  * table grants (INSERT/UPDATE/DELETE/SELECT) per role, from information_schema.role_table_grants;
  * sequences owned by those tables and their USAGE/SELECT grants (a serial/identity bypass path);
  * SECURITY DEFINER functions whose body references the tables (an indirect write path that a
    plain table REVOKE would NOT close);
  * role memberships (can the platform role ``SET ROLE`` to a stronger role?).

Plus a top-level ``role_separation_confirmed`` verdict when both platform and service URLs are given.

Usage (any subset; at least one connection required):
    DECISION_SOR_PLATFORM_URL=postgres://sahool_app...      \
    DECISION_SOR_SERVICE_URL=postgres://decision_service... \
    python services/decision-service/decision_sor_role_certify.py

Optional:
    DECISION_SOR_TABLE_SCHEMA=public   # schema holding the SoR tables (default: public)
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

# The five platform-owned SoR tables (kept in lockstep with platform_sor_revoke.PLATFORM_SOR_TABLES).
SOR_TABLES: tuple[str, ...] = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
)


async def _connect(url: str):
    try:
        import asyncpg  # type: ignore
    except ImportError as exc:  # pragma: no cover - deploy/runtime dependency
        raise SystemExit("asyncpg is required for role certification") from exc
    return await asyncpg.connect(url, statement_cache_size=0)


async def _role_attributes(conn: Any, role: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolcanlogin, rolinherit "
        "FROM pg_roles WHERE rolname=$1",
        role,
    )
    return dict(row) if row else {}


async def _memberships(conn: Any, role: str) -> list[str]:
    # Roles that `role` is a member of (i.e. roles it may SET ROLE to).
    rows = await conn.fetch(
        """
        SELECT g.rolname AS grantor_role
        FROM pg_auth_members m
        JOIN pg_roles r ON r.oid = m.member
        JOIN pg_roles g ON g.oid = m.roleid
        WHERE r.rolname = $1
        """,
        role,
    )
    return sorted(row["grantor_role"] for row in rows)


async def _table_owner(conn: Any, schema: str, table: str) -> str | None:
    return await conn.fetchval(
        "SELECT tableowner FROM pg_tables WHERE schemaname=$1 AND tablename=$2", schema, table
    )


async def _table_grants(conn: Any, schema: str, table: str) -> dict[str, list[str]]:
    rows = await conn.fetch(
        """
        SELECT grantee, privilege_type
        FROM information_schema.role_table_grants
        WHERE table_schema=$1 AND table_name=$2
        ORDER BY grantee, privilege_type
        """,
        schema,
        table,
    )
    grants: dict[str, list[str]] = {}
    for row in rows:
        grants.setdefault(row["grantee"], []).append(row["privilege_type"])
    return grants


async def _sequences_for_tables(conn: Any, schema: str, tables: tuple[str, ...]) -> dict[str, Any]:
    # Sequences owned by (serial/identity of) the SoR tables + their USAGE/SELECT grants.
    rows = await conn.fetch(
        """
        SELECT DISTINCT s.relname AS sequence_name, t.relname AS table_name
        FROM pg_depend d
        JOIN pg_class s ON s.oid = d.objid AND s.relkind = 'S'
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = $1 AND t.relname = ANY($2::text[])
        """,
        schema,
        list(tables),
    )
    out: dict[str, Any] = {}
    for row in rows:
        seq = row["sequence_name"]
        grants = await conn.fetch(
            """
            SELECT grantee, privilege_type
            FROM information_schema.role_usage_grants
            WHERE object_schema=$1 AND object_name=$2
            ORDER BY grantee, privilege_type
            """,
            schema,
            seq,
        )
        g: dict[str, list[str]] = {}
        for gr in grants:
            g.setdefault(gr["grantee"], []).append(gr["privilege_type"])
        out[seq] = {"table": row["table_name"], "grants": g}
    return out


async def _security_definer_writers(conn: Any, tables: tuple[str, ...]) -> list[dict[str, Any]]:
    # SECURITY DEFINER functions whose body textually references any SoR table — an indirect write
    # path a plain table REVOKE does NOT close (flagged for manual review, not auto-judged).
    rows = await conn.fetch(
        """
        SELECT n.nspname AS schema, p.proname AS function, r.rolname AS owner
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_roles r ON r.oid = p.proowner
        WHERE p.prosecdef = true
          AND (SELECT bool_or(position(t IN COALESCE(p.prosrc, '')) > 0) FROM unnest($1::text[]) AS t)
        ORDER BY n.nspname, p.proname
        """,
        list(tables),
    )
    return [dict(row) for row in rows]


async def _certify_connection(url: str, schema: str) -> dict[str, Any]:
    conn = await _connect(url)
    try:
        current_user = await conn.fetchval("SELECT current_user")
        session_user = await conn.fetchval("SELECT session_user")
        return {
            "current_user": current_user,
            "session_user": session_user,
            "role_attributes": await _role_attributes(conn, current_user),
            "memberships_can_set_role_to": await _memberships(conn, current_user),
            "table_owners": {t: await _table_owner(conn, schema, t) for t in SOR_TABLES},
            "table_grants": {t: await _table_grants(conn, schema, t) for t in SOR_TABLES},
            "sequences": await _sequences_for_tables(conn, schema, SOR_TABLES),
            "security_definer_writers": await _security_definer_writers(conn, SOR_TABLES),
        }
    finally:
        await conn.close()


async def _run() -> dict[str, Any]:
    schema = os.getenv("DECISION_SOR_TABLE_SCHEMA", "public").strip() or "public"
    platform_url = os.getenv("DECISION_SOR_PLATFORM_URL", "").strip()
    service_url = os.getenv("DECISION_SOR_SERVICE_URL", "").strip()
    if not platform_url and not service_url:
        raise SystemExit(
            "at least one of DECISION_SOR_PLATFORM_URL / DECISION_SOR_SERVICE_URL is required"
        )
    result: dict[str, Any] = {"schema": schema, "sor_tables": list(SOR_TABLES)}
    if platform_url:
        result["platform"] = await _certify_connection(platform_url, schema)
    if service_url:
        result["decision_service"] = await _certify_connection(service_url, schema)
    if platform_url and service_url:
        p = result["platform"]["current_user"]
        s = result["decision_service"]["current_user"]
        result["role_separation_confirmed"] = bool(p and s and p != s)
        result["platform_role"] = p
        result["decision_service_role"] = s
    return result


def main() -> int:
    print(json.dumps(asyncio.run(_run()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
