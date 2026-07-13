"""Runtime certification for the canonical soil truth chain on real PostgreSQL.

Covers the claims that cannot be established with unit tests alone:
- v155/v156 schema presence and FORCE RLS posture;
- tenant read/write isolation under a NOBYPASSRLS role;
- canonical observation idempotency under concurrent writers;
- advisory-lock profile rebuild and logical exactly-once snapshot persistence;
- strict-cutover readiness before and after a governed profile exists.

Executed by the existing ``pytest -m integration`` CI job after all migrations are applied.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg is required for PostgreSQL certification")

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)
ROLE = "soil_runtime_cert_rls"
ROOT = Path(__file__).resolve().parent.parent
SOIL_SERVICE = ROOT / "services" / "soil-service"
if str(SOIL_SERVICE) not in sys.path:
    sys.path.insert(0, str(SOIL_SERVICE))


async def _connect():
    try:
        return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")


async def _ensure_role_and_grants(conn) -> None:
    await conn.execute(
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
            CREATE ROLE {ROLE} NOSUPERUSER NOBYPASSRLS;
          END IF;
        END $$;
        """
    )
    await conn.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    await conn.execute(
        f"GRANT SELECT, INSERT, UPDATE ON soil_observations, soil_profile_snapshots, "
        f"soil_observation_supersessions, soil_profile_current TO {ROLE}"
    )


async def _insert_observation(
    conn,
    *,
    tenant_id: str,
    field_id: str,
    observation_id: str,
    idempotency_key: str,
    property_name: str = "ph",
    value: float = 7.2,
) -> str:
    return await conn.execute(
        """
        INSERT INTO soil_observations (
          observation_id, contract_version, tenant_id, field_id, property,
          value_json, unit, depth_from_cm, depth_to_cm, observed_at, received_at,
          source_type, source_id, procedure_id, quality_status, quality_flags,
          confidence, idempotency_key, provenance
        ) VALUES (
          $1, 'soil-observation.v1', $2::uuid, $3, $4,
          to_jsonb($5::double precision), NULL, 0, 30, $6, $6,
          'field_measurement', 'runtime-cert', 'runtime-cert.v1', 'accepted', '[]'::jsonb,
          0.9, $7, '{}'::jsonb
        )
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
        """,
        observation_id,
        tenant_id,
        field_id,
        property_name,
        value,
        datetime.now(UTC),
        idempotency_key,
    )


@pytest.fixture
async def certification_context():
    conn = await _connect()
    await _ensure_role_and_grants(conn)
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    field_id = f"fld_soil_cert_{uuid.uuid4().hex[:12]}"
    context = {"tenant_a": tenant_a, "tenant_b": tenant_b, "field_id": field_id}
    try:
        yield conn, context
    finally:
        await conn.execute("RESET ROLE")
        await conn.execute("SELECT set_config('app.current_tenant', '', false)")
        # FK-safe teardown order: pointer → snapshots, supersessions → observations,
        # plus projection queue rows keyed by field.
        await conn.execute("DELETE FROM soil_profile_current WHERE field_id=$1", field_id)
        await conn.execute("DELETE FROM soil_profile_snapshots WHERE field_id=$1", field_id)
        await conn.execute("DELETE FROM soil_profile_projection_jobs WHERE field_id=$1", field_id)
        await conn.execute(
            """
            DELETE FROM soil_observation_supersessions
            WHERE superseded_observation_id IN (
                SELECT observation_id FROM soil_observations WHERE field_id=$1
            )
            """,
            field_id,
        )
        await conn.execute("DELETE FROM soil_observations WHERE field_id=$1", field_id)
        await conn.close()


async def test_v155_v156_schema_and_force_rls(certification_context):
    conn, _ = certification_context
    required = {
        "soil_observations",
        "soil_profile_snapshots",
        "lab_samples",
        "lab_sample_custody_events",
        "soil_lab_results",
        "water_lab_result_sets",
        "soil_observation_supersessions",
        "soil_profile_current",
    }
    rows = await conn.fetch(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname = ANY($1::text[])
        """,
        sorted(required),
    )
    assert {r["relname"] for r in rows} == required
    assert all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in rows)

    policies = await conn.fetch(
        """
        SELECT tablename, policyname, qual, with_check
        FROM pg_policies
        WHERE schemaname='public' AND tablename = ANY($1::text[])
        """,
        sorted(required),
    )
    by_table = {r["tablename"]: r for r in policies if r["policyname"] == "tenant_isolation"}
    assert set(by_table) == required
    assert all("app.current_tenant" in (r["qual"] or "") for r in by_table.values())
    assert all("app.current_tenant" in (r["with_check"] or "") for r in by_table.values())


async def test_soil_rls_read_and_write_isolation(certification_context):
    conn, ctx = certification_context
    await _insert_observation(
        conn,
        tenant_id=ctx["tenant_a"],
        field_id=ctx["field_id"],
        observation_id=f"obs_{uuid.uuid4().hex}",
        idempotency_key="tenant-a",
    )
    await _insert_observation(
        conn,
        tenant_id=ctx["tenant_b"],
        field_id=ctx["field_id"],
        observation_id=f"obs_{uuid.uuid4().hex}",
        idempotency_key="tenant-b",
    )

    await conn.execute(f"SET ROLE {ROLE}")
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", ctx["tenant_a"])
    visible = await conn.fetch(
        "SELECT tenant_id::text FROM soil_observations WHERE field_id=$1", ctx["field_id"]
    )
    assert [r["tenant_id"] for r in visible] == [ctx["tenant_a"]]

    with pytest.raises(asyncpg.PostgresError):
        await _insert_observation(
            conn,
            tenant_id=ctx["tenant_b"],
            field_id=ctx["field_id"],
            observation_id=f"obs_{uuid.uuid4().hex}",
            idempotency_key="cross-tenant-blocked",
        )
    await conn.execute("RESET ROLE")


async def test_concurrent_idempotency_and_profile_rebuild(certification_context):
    _conn, ctx = certification_context
    tenant_id = ctx["tenant_a"]
    field_id = ctx["field_id"]
    idem = f"same-{uuid.uuid4().hex}"

    async def writer(index: int) -> str:
        conn = await _connect()
        try:
            return await _insert_observation(
                conn,
                tenant_id=tenant_id,
                field_id=field_id,
                observation_id=f"obs_{index}_{uuid.uuid4().hex}",
                idempotency_key=idem,
            )
        finally:
            await conn.close()

    results = await asyncio.gather(*(writer(i) for i in range(16)))
    assert sum(result.endswith("1") for result in results) == 1

    import soil_store

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=8, statement_cache_size=0)
    try:
        before = await soil_store.get_cutover_readiness(pool, tenant_id=tenant_id)
        assert before["fields_total"] == 1
        assert before["profiles_missing"] == 1
        assert before["can_enable_strict_soil"] is False

        snapshots = await asyncio.gather(
            *(
                soil_store.rebuild_snapshot_locked(pool, tenant_id=tenant_id, field_id=field_id)
                for _ in range(12)
            )
        )
        hashes = {snapshot.profile_hash for snapshot in snapshots}
        assert len(hashes) == 1

        conn = await _connect()
        try:
            count = await conn.fetchval(
                """
                SELECT count(*) FROM soil_profile_snapshots
                WHERE tenant_id=$1::uuid AND field_id=$2
                """,
                tenant_id,
                field_id,
            )
        finally:
            await conn.close()
        assert count == 1

        after = await soil_store.get_cutover_readiness(pool, tenant_id=tenant_id)
        assert after["profiles_ready"] == 1
        assert after["profiles_missing"] == 0
        assert after["invalid_profiles"] == 0
        assert after["coverage_pct"] == 100.0
        assert after["can_enable_strict_soil"] is True
    finally:
        await pool.close()


async def test_supersession_correction_flips_current_pointer(certification_context):
    """End-to-end on real PostgreSQL: a governed lab correction supersedes the original,
    flips the explicit current pointer, and excludes the superseded reading — even though the
    correction shares the sampling time (effective_at does not advance)."""
    _conn, ctx = certification_context
    tenant_id = ctx["tenant_a"]
    field_id = ctx["field_id"]
    sampled = datetime.now(UTC)

    import soil_store

    from shared.contracts.soil import SoilObservation

    def _obs(idem, value, received, supersedes=None):
        return SoilObservation(
            tenant_id=tenant_id,
            field_id=field_id,
            property="ph",
            value=value,
            unit="pH",
            depth_from_cm=0,
            depth_to_cm=30,
            observed_at=sampled,
            received_at=received,
            source_type="laboratory",
            quality_status="accepted",
            idempotency_key=idem,
            supersedes_observation_id=supersedes,
        )

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=6, statement_cache_size=0)
    try:
        original = _obs("ph-orig", 7.9, sampled)
        assert await soil_store.persist_observation(pool, original) is True
        first = await soil_store.rebuild_snapshot_locked(
            pool, tenant_id=tenant_id, field_id=field_id
        )
        current = await soil_store.get_current_snapshot(
            pool, tenant_id=tenant_id, field_id=field_id
        )
        assert current["profile_hash"] == first.profile_hash

        correction = _obs(
            "ph-fix",
            7.1,
            sampled + timedelta(hours=6),
            supersedes=original.observation_id,
        )
        assert await soil_store.persist_observation(pool, correction) is True
        second = await soil_store.rebuild_snapshot_locked(
            pool, tenant_id=tenant_id, field_id=field_id
        )

        assert second.profile_hash != first.profile_hash
        assert second.effective_at == first.effective_at
        current = await soil_store.get_current_snapshot(
            pool, tenant_id=tenant_id, field_id=field_id
        )
        assert current["profile_hash"] == second.profile_hash
        assert float(current["layers"][0]["properties"]["ph"]["value"]) == 7.1

        # The superseded original is flagged and excluded; exactly one current pointer row.
        observations = await soil_store.list_observations(
            pool, tenant_id=tenant_id, field_id=field_id
        )
        superseded = {o["observation_id"]: o["is_superseded"] for o in observations}
        assert superseded.get(original.observation_id) is True
        assert superseded.get(correction.observation_id) is False

        async with pool.acquire() as conn:
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
            pointer_count = await conn.fetchval(
                "SELECT count(*) FROM soil_profile_current "
                "WHERE tenant_id=$1::uuid AND field_id=$2",
                tenant_id,
                field_id,
            )
        assert pointer_count == 1
    finally:
        await pool.close()
