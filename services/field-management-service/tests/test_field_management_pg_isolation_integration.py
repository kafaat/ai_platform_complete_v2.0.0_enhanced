"""field-management-service — live PostgreSQL RLS tenant-isolation integration test.

Marked `integration` — runs only when a live PostgreSQL with the `fields` table and
a NOBYPASSRLS `sahool_app` role is available (staging/CI integration job), never in
the unit gate. Proves the two properties the unit contract test can only assert
statically:

  1. spoofed tenant: a valid service token + tenant A cannot read a field owned by
     tenant B even with the exact field_id ⇒ 404 (no cross-tenant disclosure).
  2. connection-reuse isolation: sequential reads for tenant A then tenant B do NOT
     leak the `app.current_tenant` GUC (set_config is transaction-local, per-request
     connection), so tenant B never sees tenant A's row.

A superuser / BYPASSRLS role would make RLS vacuous; the DSN must be the restricted
sahool_app role for this test to be meaningful.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

SERVICE_DIR = Path(__file__).resolve().parents[1]
MAIN_PATH = SERVICE_DIR / "main.py"


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn or "sahool_app" not in dsn:
        pytest.skip("DATABASE_URL on the NOBYPASSRLS sahool_app role is required")
    return dsn


def _load_main():
    pytest.importorskip("fastapi")
    pytest.importorskip("asyncpg")
    spec = importlib.util.spec_from_file_location("field_management_main_integration", MAIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


async def _seed_field(dsn: str, tenant_id: str, field_id: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
            await conn.execute(
                "INSERT INTO fields (field_id, tenant_id, name) VALUES ($1, $2::uuid, $3) "
                "ON CONFLICT (field_id) DO NOTHING",
                field_id,
                tenant_id,
                f"iso-{field_id}",
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cross_tenant_read_is_404_and_no_connection_leak():
    from fastapi import HTTPException

    dsn = _dsn()
    mod = _load_main()
    mod.DATABASE_URL = dsn

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    field_a = f"fld_iso_{uuid.uuid4().hex[:12]}"
    await _seed_field(dsn, tenant_a, field_a)

    # tenant A reads its own field
    got = await mod.internal_get_field(field_a, tenant=tenant_a)
    assert got["field_id"] == field_a

    # spoofed tenant: tenant B cannot read tenant A's field even with the exact id ⇒ 404
    with pytest.raises(HTTPException) as e:
        await mod.internal_get_field(field_a, tenant=tenant_b)
    assert e.value.status_code == 404

    # connection-reuse isolation: A's list then B's list — B must not see A's row
    a_list = await mod.internal_list_fields(tenant=tenant_a)
    b_list = await mod.internal_list_fields(tenant=tenant_b)
    assert any(r["field_id"] == field_a for r in a_list)
    assert all(r["field_id"] != field_a for r in b_list)
