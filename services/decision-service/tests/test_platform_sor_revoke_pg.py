"""Behavioral proof (real Postgres): the cutover REVOKE strips platform writes but keeps SELECT.

This is the DB-level enforcement that backs the app-layer guard
(``sahool-platform decision_sor_mode.assert_platform_may_write_decision_sor``): after demotion a
platform write must fail *at the database*, even if the Python guard is bypassed. SELECT is
retained (platform stays a read-side facade). ``--grant`` is the exact inverse (rollback).

Runs in the Decision Service Tests job (which provides a superuser ``DATABASE_URL`` and applies
migrations 001+, so the five SoR tables exist). Skipped when DATABASE_URL is absent so local
``pytest`` without a DB stays green.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import platform_sor_revoke as psr  # noqa: E402

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")

# A throwaway stand-in for the platform app role (e.g. sahool_app). NOLOGIN — privilege-only.
PROBE_ROLE = "sor_revoke_probe_role"


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _drop_probe(conn) -> None:
    # A role cannot be dropped while it holds grants — revoke everything on the SoR tables first.
    for table in psr.PLATFORM_SOR_TABLES:
        await conn.execute(f'REVOKE ALL ON "public"."{table}" FROM "{PROBE_ROLE}"')
    await conn.execute(f'DROP ROLE IF EXISTS "{PROBE_ROLE}"')


async def _all_writes(conn, table: str) -> list[bool]:
    return [
        bool(
            await conn.fetchval(
                "SELECT has_table_privilege($1, $2, $3)", PROBE_ROLE, f"public.{table}", p
            )
        )
        for p in psr.WRITE_PRIVILEGES
    ]


def test_revoke_removes_writes_keeps_select_and_grant_restores() -> None:
    async def _run():
        conn = await _connect()
        try:
            await conn.execute(f'DROP ROLE IF EXISTS "{PROBE_ROLE}"')
            await conn.execute(f'CREATE ROLE "{PROBE_ROLE}" NOLOGIN')
            # Simulate the pre-cutover platform grant: full writes + read on the five SoR tables.
            for table in psr.PLATFORM_SOR_TABLES:
                await conn.execute(
                    f'GRANT INSERT, UPDATE, DELETE, SELECT ON "public"."{table}" TO "{PROBE_ROLE}"'
                )

            # Baseline: every write privilege present.
            for table in psr.PLATFORM_SOR_TABLES:
                assert all(await _all_writes(conn, table)), f"baseline writes missing on {table}"

            # Cutover REVOKE.
            await psr.revoke_platform_writes(conn, PROBE_ROLE)
            for table in psr.PLATFORM_SOR_TABLES:
                assert not any(await _all_writes(conn, table)), f"writes survived revoke on {table}"
                keeps_select = await conn.fetchval(
                    "SELECT has_table_privilege($1, $2, 'SELECT')", PROBE_ROLE, f"public.{table}"
                )
                assert keeps_select, f"SELECT must be retained on {table}"

            # Rollback GRANT restores writes.
            await psr.grant_platform_writes(conn, PROBE_ROLE)
            for table in psr.PLATFORM_SOR_TABLES:
                assert all(await _all_writes(conn, table)), (
                    f"grant did not restore writes on {table}"
                )

            # The decision-service-owned outbox is NOT in the platform target set.
            assert "decision_outbox_events" not in psr.PLATFORM_SOR_TABLES
        finally:
            await _drop_probe(conn)
            await conn.close()

    asyncio.run(_run())
