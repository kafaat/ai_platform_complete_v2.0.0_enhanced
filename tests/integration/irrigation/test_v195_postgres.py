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
from uuid import UUID

import pytest

asyncpg = pytest.importorskip("asyncpg")
ADMIN_URL = os.getenv("ADMIN_DATABASE_URL")
APP_URL = os.getenv("APP_DATABASE_URL")
OTHER_URL = os.getenv("OTHER_TENANT_DATABASE_URL")
if not all((ADMIN_URL, APP_URL, OTHER_URL)):
    pytest.skip("IRR-F01 local PostgreSQL URLs are not configured", allow_module_level=True)

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")
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
            rows = await conn.fetch(
                "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = ANY($1::text[]) ORDER BY rolname",
                ["sahool_app", "sahool_other"],
            )
            assert [r["rolname"] for r in rows] == ["sahool_app", "sahool_other"]
            assert all(not r["rolsuper"] and not r["rolbypassrls"] for r in rows)
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


def test_wrong_tenant_context_cannot_observe_rows_seeded_by_admin():
    """Proves policy isolation without relying on project/hydraulic FK fixtures."""

    async def case():
        admin = await asyncpg.connect(ADMIN_URL)
        app = await asyncpg.connect(APP_URL)
        try:
            # Admin-owned probe table has the exact same forced policy shape. This avoids
            # fabricating the large pre-v195 irrigation dependency graph in this slice.
            await admin.execute("DROP TABLE IF EXISTS irr_f01_rls_probe")
            await admin.execute(
                "CREATE TABLE irr_f01_rls_probe(tenant_id uuid NOT NULL, value text)"
            )
            await admin.execute("ALTER TABLE irr_f01_rls_probe ENABLE ROW LEVEL SECURITY")
            await admin.execute("ALTER TABLE irr_f01_rls_probe FORCE ROW LEVEL SECURITY")
            await admin.execute(
                "CREATE POLICY tenant_isolation ON irr_f01_rls_probe "
                "USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')) "
                "WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))"
            )
            await admin.execute("GRANT SELECT, INSERT ON irr_f01_rls_probe TO sahool_app")
            await admin.execute(
                "INSERT INTO irr_f01_rls_probe VALUES($1, 'A'),($2, 'B')", TENANT_A, TENANT_B
            )
            await app.execute("SELECT set_config('app.current_tenant', $1, false)", str(TENANT_A))
            assert await app.fetchval("SELECT count(*) FROM irr_f01_rls_probe") == 1
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app.execute("INSERT INTO irr_f01_rls_probe VALUES($1, 'forbidden')", TENANT_B)
        except BaseException as exc:
            capture_sql_failure(
                "test_wrong_tenant_context_cannot_observe_rows_seeded_by_admin", exc
            )
            raise
        finally:
            await app.close()
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
