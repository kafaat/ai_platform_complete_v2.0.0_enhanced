"""W1-04 (``soil-2``): the hydraulic profile follows the soil snapshot without a manual call.

Before W1-04 ``soil_hydraulic_profiles`` was written only by ``POST
/v1/fields/{id}/soil/hydraulic-profile/rebuild``, which nothing calls, so ``GET
.../hydraulic-profile`` answered 404 and the platform's canonical root zone stayed blocked.
Now every snapshot rebuild projects the profile in the same transaction, keyed by the
snapshot's ``profile_hash``, and the GET serves the profile of the *current* snapshot.

Measured over HTTP against soil-service's real app on a migrated PostgreSQL, as the
NOSUPERUSER/NOBYPASSRLS role (``TEST_DATABASE_URL``):

1. POST evidence ⇒ GET hydraulic-profile is 200 with the POST's ``profile_hash`` (contract);
2. new evidence moves the hash ⇒ the GET follows it;
3. a rebuild that lands on the same hash keeps the stored profile (no churn);
4. negative controls: a field with no evidence is 404; a profile stored for a hash that is not
   the current snapshot's is never served, even when it is the newest row.

Run: ``TEST_DATABASE_URL=… pytest -m integration <this file>``.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests_v9.service_module import load_service_main

pytestmark = [pytest.mark.integration, pytest.mark.slow]

asyncpg = pytest.importorskip("asyncpg")
httpx = pytest.importorskip("httpx")

ROOT = Path(__file__).resolve().parents[1]
SOIL = ROOT / "services" / "soil-service"
DSN = os.getenv("TEST_DATABASE_URL") or ""
TOKEN = secrets.token_hex(20)
_SOIL_MODULES = (
    "main",
    "router_registry",
    "routers",
    "soil_store",
    "p1_store",
    "p2_store",
    "p3_store",
    "p1_products",
    "profile_composer",
    "jsonb_values",
    "db_persist",
)


async def _probe() -> str:
    if not DSN:
        return "TEST_DATABASE_URL is not set"
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("soil_hydraulic_profiles", "soil_profile_current"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _owned(name: str) -> bool:
    return any(name == n or name.startswith(n + ".") for n in _SOIL_MODULES)


@pytest.fixture(scope="module")
def soil_main():
    """The soil service's own import graph, isolated and restored afterwards."""
    previous = {k: v for k, v in sys.modules.items() if _owned(k)}
    for key in previous:
        del sys.modules[key]
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.syspath_prepend(str(SOIL))
            # No field-owner lookup DB: the owner is unresolved, so tenancy rests on X-Tenant-Id
            # and RLS (the same posture as test_soil_jsonb_stores_live_pg).
            mp.setenv("DATABASE_URL", "")
            mp.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
            main = load_service_main(str(SOIL), required_attrs=("_REQ_TENANT", "_pool", "app"))
            importlib.import_module("p1_store")
            yield main
    finally:
        for key in [k for k in sys.modules if _owned(k)]:
            del sys.modules[key]
        sys.modules.update(previous)


def _observation(tenant: str, field_id: str, prop: str, value: float, unit: str, age_h: int):
    return {
        "tenant_id": tenant,
        "field_id": field_id,
        "property": prop,
        "value": value,
        "unit": unit,
        "depth_from_cm": 0,
        "depth_to_cm": 30,
        "observed_at": (datetime.now(UTC) - timedelta(hours=age_h)).isoformat(),
        "source_type": "laboratory",
        "source_id": f"lab-{prop}-{age_h}",
        "idempotency_key": f"w104-{uuid.uuid4().hex}",
    }


def _run(soil_main, case):
    async def body():
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3)
        tenant, field_id = str(uuid.uuid4()), f"w104-{uuid.uuid4().hex[:10]}"
        previous_pool = soil_main._pool
        soil_main._pool = pool
        transport = httpx.ASGITransport(app=soil_main.app)
        headers = {"X-Agent-Token": TOKEN, "X-Tenant-Id": tenant}
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://soil", headers=headers
            ) as client:
                await case(client, pool, tenant, field_id)
        finally:
            soil_main._pool = previous_pool
            # Observation writes enqueue a projection job; the database is shared with other
            # integration tests whose worker claims the oldest pending job of any tenant.
            try:
                async with pool.acquire() as conn, conn.transaction():
                    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
                    await conn.execute(
                        """DELETE FROM soil_profile_projection_jobs
                           WHERE tenant_id=$1::uuid AND field_id=$2""",
                        tenant,
                        field_id,
                    )
            finally:
                await pool.close()

    asyncio.run(body())


async def _post(client, tenant, field_id, prop, value, unit, age_h=2):
    response = await client.post(
        "/v1/soil/observations", json=_observation(tenant, field_id, prop, value, unit, age_h)
    )
    assert response.status_code == 201, (
        f"POST evidence failed: {response.status_code} {response.text}"
    )
    return response.json()


def test_post_evidence_then_get_hydraulic_profile_carries_the_snapshot_hash(soil_main):
    async def case(client, pool, tenant, field_id):
        await _post(client, tenant, field_id, "field_capacity", 0.31, "m3/m3")
        posted = await _post(client, tenant, field_id, "wilting_point", 0.12, "m3/m3")

        got = await client.get(f"/v1/fields/{field_id}/soil/hydraulic-profile")
        assert got.status_code == 200, (
            f"no hydraulic profile after evidence (soil-2 not fixed): {got.status_code} {got.text}"
        )
        body = got.json()
        assert body["source_soil_profile_hash"] == posted["profile_hash"], (
            f"hydraulic profile hash {body['source_soil_profile_hash']} != snapshot hash "
            f"{posted['profile_hash']}"
        )
        assert body["tenant_id"] == tenant and body["field_id"] == field_id, (
            f"profile identity does not match the request: {body['tenant_id']}/{body['field_id']}"
        )
        layer = body["layers"][0]
        assert layer["field_capacity"]["value"] == 0.31, f"field capacity: {layer}"
        assert layer["field_capacity"]["origin"] == "measured", f"origin: {layer}"
        assert body["executable"] is True, f"FC+WP measured, profile must execute: {body}"

        current = await client.get(f"/v1/fields/{field_id}/soil/profile")
        assert current.status_code == 200, f"current snapshot: {current.status_code}"
        assert current.json()["profile_hash"] == body["source_soil_profile_hash"], (
            "GET hydraulic-profile does not describe the current snapshot"
        )

    _run(soil_main, case)


def test_new_evidence_moves_the_projection_and_same_hash_keeps_the_profile(soil_main):
    async def case(client, pool, tenant, field_id):
        await _post(client, tenant, field_id, "field_capacity", 0.31, "m3/m3", age_h=5)
        first = await _post(client, tenant, field_id, "wilting_point", 0.12, "m3/m3", age_h=5)
        before = (await client.get(f"/v1/fields/{field_id}/soil/hydraulic-profile")).json()
        assert before["source_soil_profile_hash"] == first["profile_hash"], "first projection"

        # A rebuild on unchanged evidence lands on the same hash: the stored profile stays.
        rebuilt = await client.post(f"/v1/fields/{field_id}/soil/profile/rebuild")
        assert rebuilt.status_code == 200, f"rebuild: {rebuilt.status_code} {rebuilt.text}"
        assert rebuilt.json()["profile_hash"] == first["profile_hash"], "rebuild changed the hash"
        same = (await client.get(f"/v1/fields/{field_id}/soil/hydraulic-profile")).json()
        assert same["profile_id"] == before["profile_id"], (
            "same snapshot hash re-projected a new profile (churn): "
            f"{before['profile_id']} -> {same['profile_id']}"
        )

        # Newer evidence changes the snapshot hash; the GET follows it with no manual call.
        second = await _post(client, tenant, field_id, "field_capacity", 0.27, "m3/m3", age_h=1)
        assert second["profile_hash"] != first["profile_hash"], "new evidence kept the hash"
        after = (await client.get(f"/v1/fields/{field_id}/soil/hydraulic-profile")).json()
        assert after["source_soil_profile_hash"] == second["profile_hash"], (
            f"projection did not follow the new snapshot: {after['source_soil_profile_hash']}"
        )
        assert after["layers"][0]["field_capacity"]["value"] == 0.27, f"{after['layers'][0]}"

    _run(soil_main, case)


def test_no_evidence_is_404_and_a_stale_hash_profile_is_never_served(soil_main):
    async def case(client, pool, tenant, field_id):
        empty = await client.get(f"/v1/fields/{field_id}/soil/hydraulic-profile")
        assert empty.status_code == 404, f"no evidence must be unavailable, got {empty.status_code}"

        await _post(client, tenant, field_id, "field_capacity", 0.31, "m3/m3")
        posted = await _post(client, tenant, field_id, "wilting_point", 0.12, "m3/m3")
        good = (await client.get(f"/v1/fields/{field_id}/soil/hydraulic-profile")).json()

        # The newest row, but for a hash that is not the current snapshot's: "latest row"
        # would serve it; the current-snapshot read must not.
        stale = dict(good, profile_id=f"shp_{uuid.uuid4().hex}", source_soil_profile_hash="f" * 64)
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant_id', $1, true)", tenant)
            await conn.execute(
                """INSERT INTO soil_hydraulic_profiles(hydraulic_profile_id,tenant_id,field_id,
                       source_soil_profile_hash,payload,created_at)
                   VALUES($1,$2,$3,$4,$5::jsonb,now() + interval '1 hour')""",
                stale["profile_id"],
                tenant,
                field_id,
                stale["source_soil_profile_hash"],
                json.dumps(stale),
            )
        served = (await client.get(f"/v1/fields/{field_id}/soil/hydraulic-profile")).json()
        assert served["source_soil_profile_hash"] == posted["profile_hash"], (
            f"a profile for a non-current hash was served: {served['source_soil_profile_hash']}"
        )

        other = await client.get(
            f"/v1/fields/{field_id}/soil/hydraulic-profile",
            headers={"X-Tenant-Id": str(uuid.uuid4())},
        )
        assert other.status_code == 404, f"another tenant read the profile: {other.status_code}"

    _run(soil_main, case)
