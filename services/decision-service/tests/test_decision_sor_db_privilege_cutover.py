"""Behavioral proof (real Postgres, TWO distinct roles): the SoR write boundary is a DB privilege
boundary, not just a Python guard.

The DECISION-SOR REVOKE only means something if the platform and decision-service connect as
DIFFERENT Postgres roles. This test creates two independent LOGIN roles — ``platform_test`` and
``decision_service_test``, both NOSUPERUSER / NOBYPASSRLS / NOCREATEROLE — grants the pre-cutover
state, applies the cutover (revoke platform writes + grant service writes), then proves the boundary
*by connecting as each role*:

  * after cutover, ``platform_test`` can SELECT but INSERT/UPDATE/DELETE raise the DB's
    ``InsufficientPrivilegeError`` — NOT a Python guard;
  * ``decision_service_test`` retains write access (its INSERT gets past the privilege check —
    it fails, if at all, only on a column constraint, never on permission);
  * the catalog (``information_schema.role_table_grants``) agrees with the behavior;
  * neither role OWNS the tables (owner keeps privileges even after REVOKE — a real bypass);
  * no sequence or SECURITY DEFINER function opens a side-channel write for ``platform_test``;
  * ``platform_test`` cannot ``SET ROLE`` to a stronger role, and is not superuser/bypassrls;
  * rollback (grant back) restores platform writes.

Runs in the Decision Service Tests job (superuser ``DATABASE_URL`` + migrations applied). Skipped
when DATABASE_URL is absent so local ``pytest`` without a DB stays green.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import platform_sor_revoke as psr  # noqa: E402

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")

PLATFORM_ROLE = "platform_test"
SERVICE_ROLE = "decision_service_test"
ROLE_PASSWORD = "cutover_probe_pw"
WRITE_PRIVS = ("INSERT", "UPDATE", "DELETE")


async def _admin():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _connect_as(role: str):
    """Open a LOGIN connection AS ``role`` (same host/port/db as DATABASE_URL, swapped creds)."""
    import asyncpg

    p = urlparse(DB)
    return await asyncpg.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=role,
        password=ROLE_PASSWORD,
        database=(p.path or "/").lstrip("/") or unquote(role),
        statement_cache_size=0,
    )


async def _drop_roles(admin) -> None:
    for role in (PLATFORM_ROLE, SERVICE_ROLE):
        for table in psr.PLATFORM_SOR_TABLES:
            await admin.execute(f'REVOKE ALL ON "public"."{table}" FROM "{role}"')
        await admin.execute(f'DROP ROLE IF EXISTS "{role}"')


async def _create_roles(admin) -> None:
    await _drop_roles(admin)
    for role in (PLATFORM_ROLE, SERVICE_ROLE):
        await admin.execute(
            f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{ROLE_PASSWORD}' "
            "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"
        )


async def _grants_for(admin, role: str, table: str) -> set[str]:
    rows = await admin.fetch(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema='public' AND table_name=$1 AND grantee=$2",
        table,
        role,
    )
    return {r["privilege_type"] for r in rows}


async def _insert_error(role: str, table: str):
    """Attempt an INSERT AS role; return the exception (or None on success)."""
    conn = await _connect_as(role)
    try:
        try:
            await conn.execute(f'INSERT INTO "public"."{table}" DEFAULT VALUES')
            return None
        except Exception as exc:  # noqa: BLE001 - we classify the exception type below
            return exc
    finally:
        await conn.close()


def test_privilege_cutover_boundary_is_enforced_by_the_database() -> None:
    async def _run():
        import asyncpg

        admin = await _admin()
        try:
            await _create_roles(admin)
            # Pre-cutover: platform is the authoritative writer; service mirrors (SELECT).
            for table in psr.PLATFORM_SOR_TABLES:
                await admin.execute(
                    f'GRANT INSERT, UPDATE, DELETE, SELECT ON "public"."{table}" TO "{PLATFORM_ROLE}"'
                )
                await admin.execute(f'GRANT SELECT ON "public"."{table}" TO "{SERVICE_ROLE}"')

            # Neither app role may OWN the SoR tables (owner bypasses REVOKE). The migration role does.
            for table in psr.PLATFORM_SOR_TABLES:
                owner = await admin.fetchval(
                    "SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename=$1",
                    table,
                )
                assert owner not in (PLATFORM_ROLE, SERVICE_ROLE), (owner, table)

            # Both app roles must be unprivileged at the ROLE level.
            for role in (PLATFORM_ROLE, SERVICE_ROLE):
                attrs = await admin.fetchrow(
                    "SELECT rolsuper, rolbypassrls, rolcreaterole FROM pg_roles WHERE rolname=$1",
                    role,
                )
                assert not attrs["rolsuper"] and not attrs["rolbypassrls"], (role, dict(attrs))
                # platform role must not be a member of any role it could SET ROLE into.
                members = await admin.fetch(
                    "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
                    "WHERE r.rolname=$1",
                    role,
                )
                assert members == [], (role, "must not be able to SET ROLE to a stronger role")

            # Baseline: platform can actually write (INSERT gets past the privilege check).
            base_err = await _insert_error(PLATFORM_ROLE, "decision_record")
            assert not isinstance(base_err, asyncpg.exceptions.InsufficientPrivilegeError), base_err

            # ---- CUTOVER: revoke platform writes + grant service writes ----
            await psr.revoke_platform_writes(admin, PLATFORM_ROLE)
            for table in psr.PLATFORM_SOR_TABLES:
                await admin.execute(
                    f'GRANT INSERT, UPDATE, DELETE ON "public"."{table}" TO "{SERVICE_ROLE}"'
                )

            for table in psr.PLATFORM_SOR_TABLES:
                # Catalog agrees: platform keeps SELECT, loses writes.
                pg = await _grants_for(admin, PLATFORM_ROLE, table)
                assert "SELECT" in pg and not (pg & set(WRITE_PRIVS)), (table, pg)
                sg = await _grants_for(admin, SERVICE_ROLE, table)
                assert set(WRITE_PRIVS) <= sg, (table, sg)

            # Behavior: platform write is denied AT THE DATABASE (not a Python guard).
            perr = await _insert_error(PLATFORM_ROLE, "decision_record")
            assert isinstance(perr, asyncpg.exceptions.InsufficientPrivilegeError), perr
            # Platform read still works.
            pconn = await _connect_as(PLATFORM_ROLE)
            try:
                await pconn.fetchval("SELECT count(*) FROM decision_record")
            finally:
                await pconn.close()
            # Service write gets PAST the privilege check (fails only on a constraint, if at all).
            serr = await _insert_error(SERVICE_ROLE, "decision_record")
            assert not isinstance(serr, asyncpg.exceptions.InsufficientPrivilegeError), serr

            # No sequence tied to the SoR tables leaves platform a serial/identity bypass.
            seqs = await admin.fetch(
                """
                SELECT s.relname AS seq
                FROM pg_depend d
                JOIN pg_class s ON s.oid=d.objid AND s.relkind='S'
                JOIN pg_class t ON t.oid=d.refobjid
                JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname='public' AND t.relname = ANY($1::text[])
                """,
                list(psr.PLATFORM_SOR_TABLES),
            )
            for row in seqs:
                has_usage = await admin.fetchval(
                    "SELECT has_sequence_privilege($1, $2, 'USAGE')", PLATFORM_ROLE, row["seq"]
                )
                assert not has_usage, f"platform retains USAGE on sequence {row['seq']}"

            # No SECURITY DEFINER function owned by a privileged role writes these tables unnoticed.
            secdef = await admin.fetch(
                """
                SELECT n.nspname AS schema, p.proname AS fn
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE p.prosecdef=true
                  AND (SELECT bool_or(position(t IN COALESCE(p.prosrc,''))>0)
                       FROM unnest($1::text[]) AS t)
                """,
                list(psr.PLATFORM_SOR_TABLES),
            )
            assert secdef == [], f"unreviewed SECURITY DEFINER writers to SoR tables: {secdef}"

            # ---- ROLLBACK: restore platform writes ----
            await psr.grant_platform_writes(admin, PLATFORM_ROLE)
            rerr = await _insert_error(PLATFORM_ROLE, "decision_record")
            assert not isinstance(rerr, asyncpg.exceptions.InsufficientPrivilegeError), rerr
        finally:
            await _drop_roles(admin)
            await admin.close()

    asyncio.run(_run())
