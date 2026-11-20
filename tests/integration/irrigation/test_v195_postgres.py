"""IRR-F01 isolated PostgreSQL gate.

Runs only when the local gate exports ADMIN_DATABASE_URL/APP_DATABASE_URL.
It intentionally uses a distinct NOBYPASSRLS application login; admin is used
for schema introspection only. Failures emit machine-readable SQLSTATE evidence.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

if os.getenv("IRR_F01_CERTIFICATION_REQUIRED") == "1":
    import asyncpg
else:
    asyncpg = pytest.importorskip("asyncpg")
ADMIN_URL = os.getenv("ADMIN_DATABASE_URL")
APP_URL = os.getenv("APP_DATABASE_URL")
OTHER_URL = os.getenv("OTHER_TENANT_DATABASE_URL")
if not all((ADMIN_URL, APP_URL, OTHER_URL)):
    if os.getenv("IRR_F01_CERTIFICATION_REQUIRED") == "1":
        raise RuntimeError("IRR-F01 certification requires admin, writer and reader URLs")
    pytest.skip("IRR-F01 local PostgreSQL URLs are not configured", allow_module_level=True)

SQLSTATE_FILE = Path(
    os.getenv("IRR_F01_SQLSTATE_FILE", "artifacts/irr-f01-local-test/failed-sql-state.json")
)


def run(coro):
    return asyncio.run(coro)


def capture_sql_failure(test_name: str, exc: BaseException) -> None:
    SQLSTATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "test": test_name,
        "exception_type": type(exc).__name__,
        "sqlstate": getattr(exc, "sqlstate", None),
        "constraint": getattr(exc, "constraint_name", None),
        "table": getattr(exc, "table_name", None),
        "column": getattr(exc, "column_name", None),
    }
    SQLSTATE_FILE.write_text(json.dumps(payload, indent=2) + "\n")


def test_rls_roles_are_not_privileged():
    async def case():
        conn = await asyncpg.connect(ADMIN_URL)
        try:
            names = []
            for url in (APP_URL, OTHER_URL):
                role = await asyncpg.connect(url)
                try:
                    names.append(await role.fetchval("select current_user"))
                finally:
                    await role.close()
            assert len(set(names)) == 2
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM pg_roles WHERE rolname = ANY($1::text[]) "
                    "AND NOT (rolsuper OR rolbypassrls OR rolinherit OR rolcreatedb OR rolcreaterole)",
                    names,
                )
                == 2
            )
        finally:
            await conn.close()

    run(case())


def test_v195_tables_rls_and_force_rls_are_enabled():
    async def case():
        conn = await asyncpg.connect(ADMIN_URL)
        try:
            rows = await conn.fetch(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = ANY($1::text[]) ORDER BY relname",
                [
                    "hydraulic_capacity_evaluations",
                    "irrigation_resource_reservation_events",
                    "irrigation_resource_reservations",
                ],
            )
            assert len(rows) == 3
            assert all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in rows)
        finally:
            await conn.close()

    run(case())


def test_missing_tenant_context_is_fail_closed():
    async def case():
        conn = await asyncpg.connect(APP_URL)
        try:
            for table in (
                "hydraulic_capacity_evaluations",
                "irrigation_resource_reservations",
                "irrigation_resource_reservation_events",
            ):
                assert await conn.fetchval(f"SELECT count(*) FROM {table}") == 0
        finally:
            await conn.close()

    run(case())


def test_reader_is_scoped_and_cannot_write():
    async def case():
        tenant, other, project = uuid4(), uuid4(), uuid4()
        admin = await asyncpg.connect(ADMIN_URL)
        writer = await asyncpg.connect(APP_URL)
        reader = await asyncpg.connect(OTHER_URL)
        try:
            await admin.execute(
                "INSERT INTO irrigation_projects(id, tenant_id, name) VALUES ($1,$2,'role proof')",
                project,
                tenant,
            )
            await writer.execute("SELECT set_config('app.current_tenant',$1,false)", str(tenant))
            insert = (
                "INSERT INTO hydraulic_capacity_evaluations(tenant_id,project_id,execution_ref_type,"
                "execution_ref_id,requested_interval,requested_flow_m3h,eligible,calculation_model_version) "
                "VALUES ($1,$2,'manual_execution','test',tstzrange(now(), now()+interval '1 hour'),1,true,'v1') "
                "RETURNING evaluation_id"
            )
            key = await writer.fetchval(insert, tenant, project)
            read = "SELECT count(*) FROM hydraulic_capacity_evaluations WHERE evaluation_id=$1"
            await reader.execute("SELECT set_config('app.current_tenant',$1,false)", str(tenant))
            assert await reader.fetchval(read, key) == 1
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await reader.fetchval(insert, tenant, project)
            await reader.execute("SELECT set_config('app.current_tenant',$1,false)", str(other))
            assert await reader.fetchval(read, key) == 0
        except Exception as exc:
            capture_sql_failure("test_reader_is_scoped_and_cannot_write", exc)
            raise
        finally:
            await reader.close()
            await writer.close()
            await admin.close()

    run(case())


def test_event_correlation_id_is_not_nullable():
    async def case():
        conn = await asyncpg.connect(ADMIN_URL)
        try:
            nullable = await conn.fetchval(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='irrigation_resource_reservation_events' "
                "AND column_name='correlation_id'"
            )
            assert nullable == "NO"
        finally:
            await conn.close()

    run(case())


def test_event_unique_constraint_treats_null_causation_as_not_distinct():
    """Schema certification for deterministic event idempotency."""

    async def case():
        conn = await asyncpg.connect(ADMIN_URL)
        try:
            definition = await conn.fetchval(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='irrigation_resource_reservation_events'::regclass "
                "AND contype='u' AND pg_get_constraintdef(oid) ILIKE '%causation_id%'"
            )
            assert definition and "NULLS NOT DISTINCT" in definition.upper()
        finally:
            await conn.close()

    run(case())
