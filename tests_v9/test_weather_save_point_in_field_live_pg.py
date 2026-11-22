"""A weather task or recommendation is saved only for a point inside the field (live PG, G1).

In the map weather window the point comes from the click and field_id from the selected field;
nothing tied them, so a window probed outside the field was saved against it. The save paths
now check the point against the tenant's stored field geometry (PostGIS ST_Covers) before
any insert. This file drives the real routes over HTTP into the platform app, against a
migrated Postgres through a NOBYPASSRLS role:

  - a point outside the field is refused (422 point_outside_field) on both save paths, and
    nothing is stored;
  - a field of another tenant answers 404 field_not_found;
  - a field with no stored geometry is refused (422 field_geometry_missing);
  - a point inside the field is saved (the positive control).

Only the weather plan is fixed (a recommended, safe spraying window); the database is real.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
RING = [[44.200, 15.300], [44.204, 15.300], [44.204, 15.304], [44.200, 15.304], [44.200, 15.300]]
INSIDE = {"lat": 15.302, "lon": 44.202}
OUTSIDE = {"lat": 15.402, "lon": 44.302}


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("field_tasks", "fields", "farms", "users", "recommendations"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import fields as fields_router
    from api.routers import weather as weather_router

    return main, fields_router, weather_router


async def _journey(monkeypatch) -> dict:
    main, fields_router, weather_router = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    tenant = str(uuid.uuid4())
    other_tenant = str(uuid.uuid4())
    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"wx_rls_{uuid.uuid4().hex[:10]}"
        await owner.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}";'
            f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{role}";'
        )

    async def setup(conn):
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4, setup=setup)
    monkeypatch.setattr(main, "_DB_POOL", pool)

    async def no_imagery(**_kwargs):
        return None

    monkeypatch.setattr(fields_router, "_kick_imagery_processing", no_imagery)

    window = {
        "operation": "spraying",
        "recommended": True,
        "priority": 0.9,
        "best": {
            "time": "+3h",
            "hour_offset": 3,
            "operation": {
                "operation": "spraying",
                "score": 0.9,
                "suitability": "optimal",
                "safe": True,
                "limiting_factors": [],
            },
        },
    }

    async def fixed_plan(**_kwargs):
        return {"operations": [window], "recommended_now": [window], "top_recommendation": window}

    monkeypatch.setattr(weather_router, "weather_operation_plan", fixed_plan)
    manager = await owner.fetchval(
        "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active)"
        " VALUES ($1, 'x', 'manager', 'manager', $2::uuid, true) RETURNING id",
        f"manager.{uuid.uuid4().hex[:8]}@example.org",
        tenant,
    )
    # A field of another tenant, and a field of this tenant with no stored geometry.
    foreign_field = f"wx-foreign-{uuid.uuid4().hex[:8]}"
    bare_field = f"wx-bare-{uuid.uuid4().hex[:8]}"
    await owner.execute(
        "INSERT INTO fields (field_id, name, tenant_id, geom) VALUES"
        " ($1, 'foreign', $2::uuid, ST_SetSRID(ST_GeomFromGeoJSON($3), 4326))",
        foreign_field,
        other_tenant,
        json.dumps({"type": "Polygon", "coordinates": [RING]}),
    )
    await owner.execute(
        "INSERT INTO fields (field_id, name, tenant_id, lat, lon) VALUES"
        " ($1, 'bare', $2::uuid, 15.302, 44.202)",
        bare_field,
        tenant,
    )
    acting = {"user": None}
    main.app.dependency_overrides[main.get_current_user] = lambda: acting["user"]

    def as_(user_id, user_role: UserRole):
        acting["user"] = UserSchema(
            user_id=str(user_id), tenant_id=tenant, role=user_role, name_ar="u"
        )

    async def counts():
        return (
            await owner.fetchval(
                "SELECT count(*) FROM field_tasks WHERE tenant_id = $1::uuid", tenant
            ),
            await owner.fetchval(
                "SELECT count(*) FROM recommendations WHERE tenant_id = $1::uuid", tenant
            ),
        )

    out: dict = {}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        ) as client:
            as_(0, UserRole.OWNER)
            farm = await client.post("/api/v1/farms", json={"name": "مزرعة"})
            out["farm"] = farm.status_code, farm.text[:300]
            as_(manager, UserRole.MANAGER)
            field = await client.post(
                "/api/v1/fields",
                json={
                    "name": "حقل",
                    "crop": "wheat",
                    "farm_id": farm.json().get("farm_id"),
                    "geometry": {"type": "Polygon", "coordinates": [RING]},
                },
            )
            out["field"] = field.status_code, field.text[:300]
            field_id = field.json().get("field_id")

            async def post(path, fid, point, **extra):
                res = await client.post(path, json={"field_id": fid, **point, **extra})
                body = (
                    res.json()
                    if res.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                detail = body.get("detail") if isinstance(body, dict) else None
                code = detail.get("reason_code") if isinstance(detail, dict) else None
                return res.status_code, code, res.text[:300]

            task = "/api/v1/weather/tasks/from-operation-plan"
            rec = "/api/v1/weather/recommendations/from-operation-plan"
            out["task_outside"] = await post(task, field_id, OUTSIDE, operation="spraying")
            out["rec_outside"] = await post(rec, field_id, OUTSIDE)
            out["counts_after_outside"] = await counts()
            out["task_foreign"] = await post(task, foreign_field, INSIDE, operation="spraying")
            out["rec_foreign"] = await post(rec, foreign_field, INSIDE)
            out["task_bare"] = await post(task, bare_field, INSIDE, operation="spraying")
            out["counts_after_refusals"] = await counts()
            out["task_inside"] = await post(task, field_id, INSIDE, operation="spraying")
            out["stored_task"] = await owner.fetchrow(
                "SELECT field_id, status FROM field_tasks WHERE tenant_id = $1::uuid", tenant
            )
            out["field_id"] = field_id
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            # `recommendations` is append-only: a row a regression wrote stays (under a random
            # tenant) rather than hiding the assertion that names the regression.
            for table in ("decision_record", "field_tasks", "fields", "farms", "users"):
                try:
                    await owner.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                        [tenant, other_tenant],
                    )
                except asyncpg.PostgresError:
                    pass
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()
    return out


def test_weather_saves_check_the_point_against_the_field_geometry(monkeypatch):
    out = asyncio.run(_journey(monkeypatch))
    assert out["farm"][0] == 201, out["farm"]
    assert out["field"][0] == 201, out["field"]

    # A point outside the field is refused on both save paths, and nothing is stored.
    assert out["task_outside"][:2] == (422, "point_outside_field"), out["task_outside"]
    assert out["rec_outside"][:2] == (422, "point_outside_field"), out["rec_outside"]
    assert out["counts_after_outside"] == (0, 0)

    # Another tenant's field is not found; a field with no stored geometry cannot be verified.
    assert out["task_foreign"][:2] == (404, "field_not_found"), out["task_foreign"]
    assert out["rec_foreign"][:2] == (404, "field_not_found"), out["rec_foreign"]
    assert out["task_bare"][:2] == (422, "field_geometry_missing"), out["task_bare"]
    assert out["counts_after_refusals"] == (0, 0)

    # Positive control: the same window, a point inside the field, is saved as a pending task.
    assert out["task_inside"][0] == 200, out["task_inside"]
    assert out["stored_task"]["field_id"] == out["field_id"]
    assert out["stored_task"]["status"] == "pending"
