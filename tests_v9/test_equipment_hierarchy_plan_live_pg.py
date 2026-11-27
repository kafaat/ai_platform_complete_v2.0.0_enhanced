"""Asset hierarchy and recorded preventive plan, on a migrated PostgreSQL (v291).

Real asyncpg pool under a NOBYPASSRLS role, real schema from the manifest, real HTTP through the
ASGI app for permission and tenant behaviour. Pins:

* a parent is accepted only inside the caller's tenant; self/cyclic parents are rejected by the
  database even for SQL issued outside the API;
* a completed scheduled service carrying a meter reading becomes the last-service baseline, and
  the existing fleet intelligence then says ``due`` or ``not_due`` from recorded data only;
* an asset with no policy stays ``not_evaluated`` -- nothing is predicted or defaulted;
* another tenant cannot see or attach to the asset, and a viewer cannot write.

Without a reachable migrated database the module is skipped and the skip says so.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        has = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns WHERE table_name='equipment' "
            "AND column_name='parent_equipment_id'"
        )
        return "" if has else "schema not migrated (equipment.parent_equipment_id missing, v291)"
    finally:
        await conn.close()


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


@pytest.fixture
async def live(monkeypatch):
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main

    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"eq_rls_{uuid.uuid4().hex[:10]}"
        await owner.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}";'
        )

    async def setup(conn):
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3, setup=setup)
    monkeypatch.setattr(main, "_DB_POOL", pool)
    tenants = (str(uuid.uuid4()), str(uuid.uuid4()))
    try:
        yield main, owner, pool, tenants
    finally:
        await owner.execute(
            "DELETE FROM equipment WHERE tenant_id = ANY($1::uuid[])", list(tenants)
        )
        await pool.close()
        if role:
            await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
        await owner.close()


def _headers(main, tenant: str, role: str) -> dict[str, str]:
    now = datetime.now(UTC)
    token = main.jwt.encode(
        {
            "sub": f"u-{role}-{tenant[:6]}",
            "tenant_id": tenant,
            "role": role,
            "name_ar": "مختبر",
            "aud": "sahool",
            "iss": "sahool-platform",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        main.JWT_SECRET,
        algorithm=main.JWT_ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


def _client(main):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")


async def _create(c, h, **body):
    body.setdefault("name", "Unit")
    body.setdefault("type", "pump")
    return await c.post("/api/v1/equipment", json=body, headers=h)


async def test_parent_link_is_tenant_scoped_and_listed(live):
    main, owner, _pool, (ta, tb) = live
    ha, hb = _headers(main, ta, "manager"), _headers(main, tb, "manager")
    async with _client(main) as c:
        station = await _create(c, ha, name="Pump station", type="other")
        assert station.status_code == 201, station.text
        sid = station.json()["equipment_id"]
        pump = await _create(c, ha, name="Pump 1", parent_equipment_id=sid)
        assert pump.status_code == 201, pump.text
        # Another tenant can neither attach under nor see the station.
        foreign = await _create(c, hb, name="Intruder", parent_equipment_id=sid)
        assert foreign.status_code == 422
        assert foreign.json()["detail"] == "parent_equipment_not_found"
        missing = await _create(c, ha, parent_equipment_id="eqp_missing")
        assert missing.status_code == 422
        listed = (await c.get("/api/v1/equipment?summary=true", headers=ha)).json()
        by_name = {a["name"]: a for a in listed["assets"]}
        assert by_name["Pump 1"]["parent_equipment_id"] == sid
        assert "parent_equipment_id" not in by_name["Pump station"]
        assert (await c.get("/api/v1/equipment?summary=true", headers=hb)).json()["assets"] == []
    # The stored link is real (owner view bypasses nothing it should not).
    assert (
        await owner.fetchval(
            "SELECT parent_equipment_id FROM equipment WHERE equipment_id = $1",
            pump.json()["equipment_id"],
        )
        == sid
    )


async def test_database_rejects_cycles_cross_tenant_and_self_parent(live):
    main, owner, _pool, (ta, tb) = live
    a, b, x = (f"eqp_t{uuid.uuid4().hex[:8]}" for _ in range(3))
    ins = (
        "INSERT INTO equipment (equipment_id, tenant_id, name, type, parent_equipment_id) "
        "VALUES ($1, $2::uuid, 'n', 'pump', $3)"
    )
    await owner.execute(ins, a, ta, None)
    await owner.execute(ins, b, ta, a)
    with pytest.raises(asyncpg.PostgresError, match="equipment_parent_cycle"):
        await owner.execute(
            "UPDATE equipment SET parent_equipment_id = $1 WHERE equipment_id = $2", b, a
        )
    with pytest.raises(asyncpg.PostgresError):  # self parent: CHECK constraint
        await owner.execute(
            "UPDATE equipment SET parent_equipment_id = $1 WHERE equipment_id = $1", a
        )
    with pytest.raises(asyncpg.PostgresError, match="equipment_parent_not_in_tenant"):
        await owner.execute(ins, x, tb, a)


async def test_completed_service_with_meter_sets_baseline_and_drives_due(live):
    main, _owner, _pool, (ta, _tb) = live
    h = _headers(main, ta, "manager")
    async with _client(main) as c:
        created = await _create(
            c, h, name="Tractor", type="tractor", operating_hours=300, service_interval_hours=250
        )
        eid = created.json()["equipment_id"]
        # Policy but no baseline: nothing is assumed, nothing is due.
        state = (await c.get("/api/v1/equipment?summary=true", headers=h)).json()["intelligence"]
        assert state["due_asset_ids"] == [] and state["not_evaluated_asset_ids"] == [eid]

        # A done service WITHOUT a reading must not invent a baseline.
        r = await c.post(
            f"/api/v1/equipment/{eid}/maintenance",
            json={"kind": "scheduled", "status": "done", "performed_date": "2026-01-01"},
            headers=h,
        )
        assert r.status_code == 201, r.text
        state = (await c.get("/api/v1/equipment?summary=true", headers=h)).json()["intelligence"]
        assert state["not_evaluated_asset_ids"] == [eid]

        # With a reading of 0 the elapsed 300h exceeds the 250h interval -> due, 50h over.
        r = await c.post(
            f"/api/v1/equipment/{eid}/maintenance",
            json={"kind": "scheduled", "status": "done", "meter_hours": 0},
            headers=h,
        )
        assert r.status_code == 201, r.text
        body = (await c.get("/api/v1/equipment?summary=true", headers=h)).json()
        assert body["intelligence"]["due_asset_ids"] == [eid]
        assert body["intelligence"]["assessments"][0]["overdue_hours"] == 50.0
        assert body["assets"][0]["last_service_hours"] == 0.0

        # A later completed service at 280h resets the baseline -> not due.
        r = await c.post(
            f"/api/v1/equipment/{eid}/maintenance",
            json={"kind": "scheduled", "status": "done", "meter_hours": 280},
            headers=h,
        )
        assert r.status_code == 201
        body = (await c.get("/api/v1/equipment?summary=true", headers=h)).json()
        assert body["intelligence"]["due_asset_ids"] == []
        assert body["intelligence"]["service_not_due"] == 1
        # A repair carrying a reading is evidence on its own row, never a baseline.
        await c.post(
            f"/api/v1/equipment/{eid}/maintenance",
            json={"kind": "repair", "status": "done", "meter_hours": 10},
            headers=h,
        )
        body = (await c.get("/api/v1/equipment?summary=true", headers=h)).json()
        assert body["assets"][0]["last_service_hours"] == 280.0


async def test_viewer_cannot_write_and_foreign_tenant_cannot_log_maintenance(live):
    main, _owner, _pool, (ta, tb) = live
    ha, hb = _headers(main, ta, "manager"), _headers(main, tb, "manager")
    async with _client(main) as c:
        eid = (await _create(c, ha, service_interval_hours=100)).json()["equipment_id"]
        viewer = await _create(c, _headers(main, ta, "viewer"))
        assert viewer.status_code == 403
        r = await c.post(
            f"/api/v1/equipment/{eid}/maintenance",
            json={"kind": "scheduled", "status": "done", "meter_hours": 5},
            headers=hb,
        )
        assert r.status_code == 404
        # Out-of-contract inputs are rejected before the database.
        assert (await _create(c, ha, service_interval_hours=0)).status_code == 422
        assert (await _create(c, ha, last_service_hours=-1)).status_code == 422
