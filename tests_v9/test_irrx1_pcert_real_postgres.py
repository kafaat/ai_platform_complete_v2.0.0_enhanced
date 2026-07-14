"""IRR-PCERT database certification for IRR-X1.1 through IRR-X1.4.

Runs in the existing integration job after the migration manifest is applied.
The test is intentionally pure asyncpg: it certifies PostgreSQL/RLS/trigger
behaviour rather than mocking the application repository layer.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.integration

DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)


def _db_available() -> bool:
    try:
        import asyncpg

        async def ping() -> None:
            conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
            await conn.close()

        asyncio.run(ping())
        return True
    except Exception:
        return False


def _digest(seed: str) -> str:
    return (seed.encode().hex() + "0" * 64)[:64]


@pytest.mark.integration
def test_irrx1_pcert_schema_rls_and_database_state_machine() -> None:
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL unavailable — IRR-PCERT integration test")
    import asyncpg

    async def check() -> None:
        conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        execution_id = uuid.uuid4()
        now = datetime.now(UTC)
        try:
            tables = {
                row["tablename"]: (row["rowsecurity"], row["forcerowsecurity"])
                for row in await conn.fetch(
                    """SELECT c.relname AS tablename, c.relrowsecurity AS rowsecurity,
                              c.relforcerowsecurity AS forcerowsecurity
                         FROM pg_class c
                        WHERE c.relname = ANY($1::text[])""",
                    [
                        "irrigation_system_specifications",
                        "irrigation_engineering_calculations",
                        "irrigation_commissioning_tests_v2",
                        "irrigation_commissioning_certificates_v2",
                        "irrigation_execution_authorizations_v2",
                        "irrigation_manual_executions",
                        "irrigation_manual_execution_events",
                        "irrigation_manual_ledger_reconciliations",
                    ],
                )
            }
            assert len(tables) == 8
            assert all(enabled and forced for enabled, forced in tables.values())

            triggers = {
                row["tgname"]
                for row in await conn.fetch(
                    """SELECT tgname FROM pg_trigger
                        WHERE NOT tgisinternal AND tgrelid = ANY(
                            ARRAY[
                              'irrigation_manual_executions'::regclass,
                              'irrigation_manual_execution_events'::regclass,
                              'irrigation_manual_ledger_reconciliations'::regclass
                            ])"""
                )
            }
            assert "irrigation_manual_executions_legal_state_guard" in triggers
            assert "manual_execution_events_append_only" in triggers
            assert "manual_ledger_reconciliations_append_only" in triggers

            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", str(tenant_a)
                )
                await conn.execute(
                    """INSERT INTO irrigation_manual_executions (
                           execution_id, tenant_id, field_id, season_id, system_id,
                           recommendation_id, recommendation_digest, execution_mode, state,
                           target_depth_mm, target_volume_m3, nominal_flow_m3_h,
                           valid_from, valid_until, idempotency_key, created_by
                       ) VALUES ($1,$2,'field-a','season-a','system-a','rec-a',$3,
                                 'manual_measured','recommended',10,1000,100,$4,$5,'pcert-key','pcert')""",
                    execution_id,
                    tenant_a,
                    _digest("recommendation"),
                    now - timedelta(hours=1),
                    now + timedelta(hours=8),
                )

                # RLS: another tenant cannot read or mutate tenant A's execution.
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", str(tenant_b)
                )
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM irrigation_manual_executions WHERE execution_id=$1",
                        execution_id,
                    )
                    == 0
                )
                assert (
                    await conn.execute(
                        "UPDATE irrigation_manual_executions SET state='cancelled' WHERE execution_id=$1",
                        execution_id,
                    )
                    == "UPDATE 0"
                )

                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", str(tenant_a)
                )

                # Direct state skipping is rejected by PostgreSQL, not merely by FastAPI.
                with pytest.raises(asyncpg.PostgresError, match="IRRX1_INVALID_DB_TRANSITION"):
                    await conn.execute(
                        "UPDATE irrigation_manual_executions SET state='confirmed' WHERE execution_id=$1",
                        execution_id,
                    )

        finally:
            await conn.close()

    asyncio.run(check())


@pytest.mark.integration
def test_irrx1_pcert_append_only_and_tenant_bound_children() -> None:
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL unavailable — IRR-PCERT integration test")
    import asyncpg

    async def check() -> None:
        conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
        tenant = uuid.uuid4()
        wrong_tenant = uuid.uuid4()
        execution_id = uuid.uuid4()
        now = datetime.now(UTC)
        try:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
                await conn.execute(
                    """INSERT INTO irrigation_manual_executions (
                           execution_id, tenant_id, field_id, season_id, system_id,
                           recommendation_id, recommendation_digest, execution_mode, state,
                           target_depth_mm, target_volume_m3, nominal_flow_m3_h,
                           valid_from, valid_until, idempotency_key, created_by
                       ) VALUES ($1,$2,'field-b','season-b','system-b','rec-b',$3,
                                 'manual_measured','recommended',8,800,80,$4,$5,'pcert-key-2','pcert')""",
                    execution_id,
                    tenant,
                    _digest("recommendation-2"),
                    now - timedelta(hours=1),
                    now + timedelta(hours=8),
                )
                await conn.execute(
                    """INSERT INTO irrigation_manual_execution_events
                       (tenant_id, execution_id, from_state, to_state, actor_id, payload, event_digest)
                       VALUES ($1,$2,NULL,'recommended','pcert','{}'::jsonb,$3)""",
                    tenant,
                    execution_id,
                    _digest("event"),
                )

                # Composite FK prevents a child row claiming another tenant's ownership.
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", str(wrong_tenant)
                )
                with pytest.raises(asyncpg.ForeignKeyViolationError):
                    async with (
                        conn.transaction()
                    ):  # savepoint; keep outer certification transaction usable
                        await conn.execute(
                            """INSERT INTO irrigation_manual_execution_events
                               (tenant_id, execution_id, from_state, to_state, actor_id, payload, event_digest)
                               VALUES ($1,$2,NULL,'recommended','pcert','{}'::jsonb,$3)""",
                            wrong_tenant,
                            execution_id,
                            _digest("wrong-tenant-event"),
                        )

                await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
                with pytest.raises(asyncpg.PostgresError, match="append-only"):
                    async with conn.transaction():  # savepoint; expected trigger rejection
                        await conn.execute(
                            "UPDATE irrigation_manual_execution_events SET actor_id='tampered' WHERE execution_id=$1",
                            execution_id,
                        )
        finally:
            await conn.close()

    asyncio.run(check())
