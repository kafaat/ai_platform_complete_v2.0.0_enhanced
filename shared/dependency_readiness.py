"""Bounded dependency probes; no domain rows or secret-bearing errors are returned."""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from pathlib import Path


async def database_ready(dsn: str, *, table: str, columns: str, owner_lookup: bool = False) -> bool:
    """Check a service-owned schema and an RLS-safe role without reading tenant data.

    Table/column arguments are source constants, never request values. The query
    plans a zero-row read under a read-only transaction. It does not certify all
    migrations, policies, or write permissions; acceptance still tests those.
    """
    if not dsn:
        return False
    connection = None
    try:
        import asyncpg

        async with asyncio.timeout(3):
            connection = await asyncpg.connect(dsn, statement_cache_size=0, timeout=2)
            async with connection.transaction(readonly=True):
                await connection.execute(
                    "SELECT set_config('app.current_tenant', $1, true)",
                    "00000000-0000-0000-0000-000000000000",
                )
                safe = await connection.fetchval(
                    """SELECT NOT r.rolsuper AND NOT r.rolbypassrls
                              AND c.relrowsecurity
                              AND (c.relforcerowsecurity OR NOT pg_has_role(r.oid, c.relowner, 'USAGE'))
                       FROM pg_roles r, pg_class c
                       WHERE r.rolname = current_user AND c.oid = to_regclass($1)""",
                    table,
                )
                if not safe:
                    return False
                await connection.fetch(f"SELECT {columns} FROM {table} LIMIT 0")
                if owner_lookup:
                    return bool(
                        await connection.fetchval(
                            "SELECT to_regprocedure('sahool_field_owner_tenant(text)') IS NOT NULL"
                        )
                    )
                return True
    except Exception:  # noqa: BLE001 - dependency failures mean not ready, never leak DSNs
        return False
    finally:
        if connection is not None:
            with contextlib.suppress(Exception):
                await connection.close(timeout=1)


async def redis_ready(url: str) -> bool:
    """Check the configured replay store without claiming a real tenant nonce."""
    if not url:
        return False
    client = None
    try:
        from redis.asyncio import Redis

        async with asyncio.timeout(3):
            client = Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
            return bool(await client.ping())
    except Exception:  # noqa: BLE001 - only a boolean leaves this probe
        return False
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.aclose(), timeout=1)


def writable_directory_ready(path: str) -> bool:
    """Write, fsync and remove a private probe; do not touch existing raster files."""
    try:
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as probe:
            probe.write(b"sahool-readiness")
            probe.flush()
            os.fsync(probe.fileno())
        return True
    except OSError:
        return False
