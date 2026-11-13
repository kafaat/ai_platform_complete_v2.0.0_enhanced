"""R-H7: soil P1/P2/P3 stores decode jsonb as asyncpg actually returns it — on a migrated PG.

asyncpg returns ``jsonb`` as ``str`` (the soil service registers no codec). ``dict(row["payload"])``
on that string raised ``ValueError``: most P1/P2/P3 endpoints answered 500, and
``/hydraulic-profile/rebuild`` always did (it also handed the stored snapshot, a dict, to a builder
that reads attributes). Observation values reached the composed profile as ``"0.31"`` instead of
``0.31``, so the pedotransfer-free hydraulic layer saw no measured field capacity at all.

Real soil-service code on a real pool; the schema is the manifest's. Integration job
(``TEST_DATABASE_URL``); skipped, and saying so, without a reachable migrated database.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests_v9.service_module import load_service_main

pytestmark = [pytest.mark.integration, pytest.mark.slow]

asyncpg = pytest.importorskip("asyncpg")

ROOT = Path(__file__).resolve().parents[1]
SOIL = ROOT / "services" / "soil-service"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
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
)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if await conn.fetchval("SELECT to_regclass('public.soil_hydraulic_profiles')") is None:
            return "schema not migrated (soil_hydraulic_profiles missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _owned(name: str) -> bool:
    return any(name == n or name.startswith(n + ".") for n in _SOIL_MODULES)


@pytest.fixture(scope="module")
def soil():
    """The soil service's own import graph, isolated and restored afterwards."""
    previous = {k: v for k, v in sys.modules.items() if _owned(k)}
    for key in previous:
        del sys.modules[key]
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.syspath_prepend(str(SOIL))
            mp.setenv("DATABASE_URL", "")
            mp.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
            main = load_service_main(str(SOIL), required_attrs=("_REQ_TENANT", "_pool"))
            yield {
                "main": main,
                "soil_store": importlib.import_module("soil_store"),
                "p1_store": importlib.import_module("p1_store"),
                "p2_store": importlib.import_module("p2_store"),
                "p3_store": importlib.import_module("p3_store"),
                "p1_router": importlib.import_module("routers.p1_products"),
            }
    finally:
        for key in [k for k in sys.modules if _owned(k)]:
            del sys.modules[key]
        sys.modules.update(previous)


def _observation(tenant: str, field_id: str, prop: str, value: float, unit: str):
    from shared.contracts.soil import SoilObservation

    return SoilObservation(
        tenant_id=tenant,
        field_id=field_id,
        property=prop,
        value=value,
        unit=unit,
        depth_from_cm=0,
        depth_to_cm=30,
        observed_at=datetime.now(UTC),
        source_type="laboratory",
        source_id=f"lab-{prop}",
        idempotency_key=f"hb-{uuid.uuid4().hex}",
    )


def _run(case):
    async def body():
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3)
        tenant, field_id = str(uuid.uuid4()), f"hb-soil-{uuid.uuid4().hex[:10]}"
        try:
            await case(pool, tenant, field_id)
        finally:
            # Observation writes enqueue a projection job for the field. The database is shared
            # with the other integration tests, and the projection worker's claim takes the
            # oldest pending job of any tenant, so a job left here is claimed in place of the
            # one a later test inserted (test_soil_p6_runtime_integration).
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


def test_hydraulic_rebuild_returns_the_stored_profile_built_from_numeric_values(soil, monkeypatch):
    main, soil_store, p1_store = soil["main"], soil["soil_store"], soil["p1_store"]

    async def case(pool, tenant, field_id):
        for prop, value, unit in (
            ("field_capacity", 0.31, "m3/m3"),
            ("wilting_point", 0.12, "m3/m3"),
            ("bulk_density", 1.35, "g/cm3"),
        ):
            await soil_store.persist_observation(
                pool, _observation(tenant, field_id, prop, value, unit)
            )
        snapshot = await soil_store.rebuild_snapshot_locked(
            pool, tenant_id=tenant, field_id=field_id
        )
        assert snapshot.layers[0].properties["field_capacity"].value == 0.31

        listed = await soil_store.list_observations(pool, tenant_id=tenant, field_id=field_id)
        assert {r["property"]: r["value_json"] for r in listed}["wilting_point"] == 0.12

        monkeypatch.setattr(main, "_pool", pool)
        token = main._REQ_TENANT.set(tenant)
        try:
            out = await soil["p1_router"].rebuild_hydraulic(field_id, x_agent_token=TOKEN)
        finally:
            main._REQ_TENANT.reset(token)
        assert isinstance(out, dict), type(out)
        layer = out["layers"][0]
        assert layer["field_capacity"]["value"] == 0.31
        assert layer["field_capacity"]["origin"] == "measured"
        latest = await p1_store.get_latest(
            pool, tenant, "soil_hydraulic_profiles", "field_id", field_id
        )
        assert latest == out

    _run(case)


def test_p2_and_p3_products_round_trip_as_objects(soil):
    p2_store, p3_store = soil["p2_store"], soil["p3_store"]

    async def case(pool, tenant, field_id):
        payload = {"product": "texture", "sand_pct": 55.0, "layers": [{"depth_cm": 30}]}
        saved = await p2_store.save_product(
            pool,
            table="soil_texture_products",
            id_column="texture_product_id",
            product_id=f"tx-{uuid.uuid4().hex[:10]}",
            tenant_id=tenant,
            field_id=field_id,
            product_type="texture",
            version="v1",
            geometry_hash="g" * 16,
            payload=payload,
        )
        assert saved == payload
        assert (
            await p2_store.get_latest(
                pool, table="soil_texture_products", tenant_id=tenant, field_id=field_id
            )
            == payload
        )

        p3_payload = {"drainage_need": "moderate", "score": 0.4}
        saved3 = await p3_store.save(
            pool,
            table="soil_drainage_assessments",
            id_column="drainage_assessment_id",
            product_id=f"dr-{uuid.uuid4().hex[:10]}",
            tenant_id=tenant,
            field_id=field_id,
            product_type="drainage",
            version="v1",
            identity_hash="h" * 16,
            payload=p3_payload,
        )
        assert saved3 == p3_payload
        assert (
            await p3_store.latest(
                pool, table="soil_drainage_assessments", tenant_id=tenant, field_id=field_id
            )
            == p3_payload
        )

    _run(case)
