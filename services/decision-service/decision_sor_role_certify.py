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
  * the full transitive role-membership closure (including PostgreSQL 16 INHERIT/SET/ADMIN options);
  * effective table/sequence privileges (``has_*_privilege``), not only direct GRANT rows.

A top-level ``classification``/``cutover_preflight_safe`` verdict is PASS only when both distinct
restricted app roles are supplied, neither owns the SoR tables, the platform membership closure is
empty, and no sequence/SECURITY DEFINER bypass remains.

Usage (both connections are required for a PASS cutover verdict; one connection may still
be inspected but is classified FAILED for cutover):
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


async def _membership_closure(conn: Any, role: str) -> list[dict[str, Any]]:
    """Return the full role-membership closure, not only direct memberships.

    A direct-only check is insufficient for a cutover role: ``platform -> role_a -> role_b`` can
    preserve inherited privileges or a SET ROLE path after a direct table REVOKE. PostgreSQL 16
    exposes membership-level INHERIT/SET/ADMIN options; preserve them in the evidence so reviewers
    can see why a chain is reachable.
    """
    rows = await conn.fetch(
        """
        WITH RECURSIVE walk AS (
            SELECT
                m.roleid,
                m.member,
                1 AS depth,
                ARRAY[m.member, m.roleid]::oid[] AS path,
                m.admin_option,
                m.inherit_option,
                m.set_option
            FROM pg_auth_members m
            JOIN pg_roles member_role ON member_role.oid = m.member
            WHERE member_role.rolname = $1

            UNION ALL

            SELECT
                m.roleid,
                m.member,
                w.depth + 1,
                w.path || m.roleid,
                (w.admin_option OR m.admin_option),
                (w.inherit_option AND m.inherit_option),
                (w.set_option AND m.set_option)
            FROM pg_auth_members m
            JOIN walk w ON m.member = w.roleid
            WHERE NOT m.roleid = ANY(w.path)
        )
        SELECT
            granted.rolname AS role,
            MIN(w.depth) AS depth,
            bool_or(w.admin_option) AS admin_option,
            bool_or(w.inherit_option) AS inherit_option,
            bool_or(w.set_option) AS set_option,
            granted.rolsuper,
            granted.rolbypassrls,
            granted.rolcreaterole,
            granted.rolcreatedb,
            granted.rolcanlogin,
            granted.rolinherit
        FROM walk w
        JOIN pg_roles granted ON granted.oid = w.roleid
        GROUP BY granted.rolname, granted.rolsuper, granted.rolbypassrls,
                 granted.rolcreaterole, granted.rolcreatedb, granted.rolcanlogin, granted.rolinherit
        ORDER BY MIN(w.depth), granted.rolname
        """,
        role,
    )
    return [dict(row) for row in rows]


async def _memberships(conn: Any, role: str) -> list[str]:
    """Backward-compatible summary of roles reachable through the membership closure."""
    return [row["role"] for row in await _membership_closure(conn, role)]


async def _table_owner(conn: Any, schema: str, table: str) -> str | None:
    return await conn.fetchval(
        "SELECT tableowner FROM pg_tables WHERE schemaname=$1 AND tablename=$2", schema, table
    )


async def _effective_table_privileges(
    conn: Any, role: str, schema: str, table: str
) -> dict[str, bool]:
    qualified = f"{schema}.{table}"
    out: dict[str, bool] = {}
    for privilege in ("INSERT", "UPDATE", "DELETE", "SELECT"):
        out[privilege] = bool(
            await conn.fetchval(
                "SELECT has_table_privilege($1, $2, $3)", role, qualified, privilege
            )
        )
    return out


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


async def _sequences_for_tables(
    conn: Any, schema: str, tables: tuple[str, ...], role: str
) -> dict[str, Any]:
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
        qualified = f"{schema}.{seq}"
        effective = {
            privilege: bool(
                await conn.fetchval(
                    "SELECT has_sequence_privilege($1, $2, $3)", role, qualified, privilege
                )
            )
            for privilege in ("USAGE", "SELECT", "UPDATE")
        }
        out[seq] = {"table": row["table_name"], "grants": g, "effective": effective}
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
        membership_closure = await _membership_closure(conn, current_user)
        return {
            "current_user": current_user,
            "session_user": session_user,
            "role_attributes": await _role_attributes(conn, current_user),
            "memberships_can_set_role_to": [row["role"] for row in membership_closure if row.get("set_option")],
            "membership_closure": membership_closure,
            "table_owners": {t: await _table_owner(conn, schema, t) for t in SOR_TABLES},
            "table_grants": {t: await _table_grants(conn, schema, t) for t in SOR_TABLES},
            "effective_table_privileges": {
                t: await _effective_table_privileges(conn, current_user, schema, t) for t in SOR_TABLES
            },
            "sequences": await _sequences_for_tables(conn, schema, SOR_TABLES, current_user),
            "security_definer_writers": await _security_definer_writers(conn, SOR_TABLES),
        }
    finally:
        await conn.close()


def _connection_blockers(label: str, evidence: dict[str, Any], app_roles: set[str]) -> list[str]:
    blockers: list[str] = []
    role = str(evidence.get("current_user") or "")
    attrs = evidence.get("role_attributes") or {}
    for key in ("rolsuper", "rolbypassrls", "rolcreaterole", "rolcreatedb"):
        if attrs.get(key) is not False:
            blockers.append(f"{label}:{role}:{key}_must_be_false")
    owners = evidence.get("table_owners") or {}
    for table in SOR_TABLES:
        owner = owners.get(table)
        if not owner:
            blockers.append(f"{label}:{table}:owner_missing")
        elif owner in app_roles:
            blockers.append(f"{label}:{table}:app_role_owns_table:{owner}")
    return blockers


def _preflight_blockers(result: dict[str, Any]) -> list[str]:
    """Judge whether the live topology is safe to proceed toward a platform-write REVOKE."""
    blockers: list[str] = []
    platform = result.get("platform")
    service = result.get("decision_service")
    if not isinstance(platform, dict) or not isinstance(service, dict):
        return ["both_platform_and_decision_service_connections_required_for_cutover"]
    if result.get("role_separation_confirmed") is not True:
        blockers.append("platform_and_decision_service_roles_must_be_distinct")
    app_roles = {str(platform.get("current_user") or ""), str(service.get("current_user") or "")}
    blockers.extend(_connection_blockers("platform", platform, app_roles))
    blockers.extend(_connection_blockers("decision_service", service, app_roles))

    # The platform role is the one being stripped of writes. Any membership keeps an ambiguity
    # surface for inherited privileges / SET ROLE after a direct REVOKE, so the cutover evidence
    # role must have an empty transitive closure (same conservative contract as live_pg_role_closure).
    closure = platform.get("membership_closure")
    if not isinstance(closure, list) or closure:
        blockers.append("platform_role_membership_closure_must_be_empty")

    for seq, item in (platform.get("sequences") or {}).items():
        effective = (item or {}).get("effective") or {}
        if any(effective.get(priv) is True for priv in ("USAGE", "SELECT", "UPDATE")):
            blockers.append(f"platform_sequence_privilege_present:{seq}")
    if platform.get("security_definer_writers"):
        blockers.append("platform_security_definer_writer_path_present")
    return sorted(set(blockers))


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
    blockers = _preflight_blockers(result)
    result["cutover_preflight_safe"] = not blockers
    result["classification"] = "PASSED" if not blockers else "FAILED"
    result["blockers"] = blockers
    return result


def main() -> int:
    result = asyncio.run(_run())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("classification") == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
