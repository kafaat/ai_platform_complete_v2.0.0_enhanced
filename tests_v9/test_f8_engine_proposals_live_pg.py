"""F8 loader on a live Postgres: stored owner proposals, tenant-bound, read-only.

``internal_service.load_stored_engine_proposals`` reads ``hourly_irrigation_mpc_schedules`` (DDL from
``migrations/v179``, applied into a throwaway schema and dropped afterwards) through a
NOBYPASSRLS role, inside a READ ONLY transaction — so any write it attempted would fail:

- the tenant's current proposal is returned with provenance and requires_human_review;
- another tenant's row is not returned (RLS and the explicit predicate);
- an expired row is withheld with a reason code;
- a field with no stored row gives an empty list with reason codes;
- flag off: nothing is read; row counts are unchanged throughout.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")

ROOT = Path(__file__).resolve().parents[1]
CORE = str(ROOT / "services" / "sahool-platform")
DDL = (ROOT / "migrations" / "v179_hourly_energy_aware_irrigation_mpc.sql").read_text(
    encoding="utf-8"
)
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if not await conn.fetchval(
            "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
        ):
            return "role cannot create the NOBYPASSRLS reader"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform_loader():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    import api.main  # noqa: F401 — main first: it registers the routers it imports last
    from api.routers.internal_service import load_stored_engine_proposals

    return load_stored_engine_proposals


_INSERT = """
INSERT INTO hourly_irrigation_mpc_schedules (
    tenant_id, field_id, season_id, solver_version, status, horizon_start, horizon_hours,
    initial_depletion_mm, final_depletion_mm, required_refill_mm, scheduled_irrigation_mm,
    scheduled_volume_m3, water_state_digest, irrigation_capability_digest,
    commissioning_executability_digest, schedule_digest, payload
) VALUES ($1::uuid, $2, 'season-fixture', 'hourly-lex-mpc.v1', 'verified', $3, 48,
          12.5, 10.0, 4.0, 4.0, 40.0, $4, $4, $4, $5, $6::jsonb)
RETURNING schedule_id::text
"""


async def _seed(conn, tenant: str, field: str, horizon_start: datetime) -> str:
    digest = uuid.uuid4().hex * 2
    payload = {
        "schema_version": "hourly_energy_aware_irrigation_mpc.v1",
        "tenant_id": tenant,
        "field_id": field,
        "decision": "irrigate",
        "recommendation_only": True,
        "execution_allowed": False,
        "initial_depletion_mm": 12.5,
        "taw_mm": 80.0,
        "raw_mm": 40.0,
        "limitations": [],
        "source_digests": {"water_state_digest": "a" * 64},
        "actions": [],
        "schedule_digest": digest,
    }
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
    return await conn.fetchval(
        _INSERT, tenant, field, horizon_start, "a" * 64, digest, json.dumps(payload)
    )


async def _measure(monkeypatch) -> dict:
    load_stored = _platform_loader()
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    schema = f"f8_{uuid.uuid4().hex[:10]}"
    role = f"f8_reader_{uuid.uuid4().hex[:10]}"
    field, empty_field = "f8-field", "f8-empty-field"
    now = datetime.now(UTC)
    owner = await asyncpg.connect(DSN)
    out: dict = {}
    try:
        await owner.execute(f'CREATE SCHEMA "{schema}"')
        await owner.execute(f'SET search_path TO "{schema}"')
        await owner.execute(DDL)
        await owner.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}";'
            f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO "{role}";'
        )
        current = await _seed(owner, tenant, field, now - timedelta(hours=1))
        expired = await _seed(owner, tenant, field, now - timedelta(hours=72))
        theirs = await _seed(owner, other, field, now - timedelta(hours=1))
        await owner.execute("SELECT set_config('app.current_tenant', '', false)")
        count_sql = "SELECT count(*) FROM hourly_irrigation_mpc_schedules"
        out["count_before"] = await owner.fetchval(count_sql)
        out["ids"] = {"current": current, "expired": expired, "theirs": theirs}

        async def load(tenant_ctx: str, tenant_arg: str, field_id: str) -> dict:
            async with owner.transaction(readonly=True):
                await owner.execute(f'SET LOCAL ROLE "{role}"')
                await owner.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_ctx)
                return await load_stored(owner, tenant_id=tenant_arg, field_id=field_id)

        monkeypatch.setenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", "true")
        out["mine"] = await load(tenant, tenant, field)
        out["cross"] = await load(tenant, other, field)  # RLS context A, asking for B
        out["empty"] = await load(tenant, tenant, empty_field)
        monkeypatch.delenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS")
        out["off"] = await load(tenant, tenant, field)
        out["count_after"] = await owner.fetchval(count_sql)
    finally:
        await owner.execute("RESET ROLE")
        await owner.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await owner.execute(f'DROP ROLE IF EXISTS "{role}"')
        await owner.close()
    return out


@pytest.fixture(scope="module")
def measured():
    monkeypatch = pytest.MonkeyPatch()
    try:
        return asyncio.run(_measure(monkeypatch))
    finally:
        monkeypatch.undo()


def test_the_tenants_current_stored_proposal_is_returned_for_review(measured):
    review = measured["mine"]
    assert review["enabled"] is True and review["read_only"] is True
    [proposal] = review["proposals"]
    assert proposal["source_record"]["record_id"] == measured["ids"]["current"]
    assert proposal["requires_human_review"] is True
    assert proposal["status"] == "awaiting_specialist_review"
    assert proposal["approved"] is False and proposal["executable"] is False
    assert proposal["amounts"]["scheduled_volume_m3"] == 40.0
    assert proposal["method"]["version"] == "hourly-lex-mpc.v1"
    for key in ("input_snapshot", "units", "timestamps", "validity", "owning_service"):
        assert proposal[key], key
    assert proposal["limitations"] == []
    assert "owner_record_expired" in review["reason_codes"], review["reason_codes"]


def test_another_tenants_row_is_never_returned(measured):
    ids = {p["source_record"]["record_id"] for p in measured["mine"]["proposals"]}
    assert measured["ids"]["theirs"] not in ids
    assert measured["cross"]["proposals"] == []
    assert "no_stored_owner_proposal" in measured["cross"]["reason_codes"]


def test_no_stored_proposal_is_empty_with_reason_codes(measured):
    assert measured["empty"]["proposals"] == []
    assert "no_stored_owner_proposal" in measured["empty"]["reason_codes"]
    assert "fertilization_owner_engine_persists_no_proposals" in measured["empty"]["reason_codes"]


def test_flag_off_reads_nothing_and_nothing_is_written(measured):
    assert measured["off"]["enabled"] is False
    assert measured["off"]["proposals"] == []
    assert measured["off"]["reason_codes"] == ["feature_flag_off"]
    assert measured["count_before"] == measured["count_after"] == 3
