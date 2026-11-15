"""A task on a field created through the API is stored (live PG, v261).

field_tasks.field_id used to reference field_boundaries, which no API path inserts into, while
POST /api/v1/fields writes `fields`. So the first task on a field drawn in the app failed the
foreign key (the chain's pin-inspection and task-imagery routes answered with an unhandled 500;
those routes are held back, and the kept weather task route answered 503). v261 points the key at
`fields`. This file drives the real routes in order, over HTTP into the platform app, against a
migrated Postgres through a NOBYPASSRLS role: create a farm (201), a field (201), then a task
from the weather operation plan (POST /api/v1/weather/tasks/from-operation-plan). The task
route declares no status code, so success is its 200 with "created": true.

Only the users row is seeded by the schema owner: accounts are provisioned by the auth service.
"""

from __future__ import annotations

import asyncio
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


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("field_tasks", "fields", "farms", "users"):
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
    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"ft_rls_{uuid.uuid4().hex[:10]}"
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

    # Creating a field queues Sentinel processing after the response; it calls other services
    # and is not what this file measures.
    async def no_imagery(**_kwargs):
        return None

    monkeypatch.setattr(fields_router, "_kick_imagery_processing", no_imagery)

    # The operation plan is read from the weather service; this file measures the task write,
    # so the plan is a fixed spraying window instead of a network call.
    async def fixed_plan(**_kwargs):
        return {"top_recommendation": {"operation": "spraying"}}

    monkeypatch.setattr(weather_router, "weather_operation_plan", fixed_plan)
    users = {}
    for name in ("manager",):
        users[name] = await owner.fetchval(
            "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active)"
            " VALUES ($1, 'x', $2, $2, $3::uuid, true) RETURNING id",
            f"{name}.{uuid.uuid4().hex[:8]}@example.org",
            name,
            tenant,
        )
    acting = {"user": None}

    def current_user():
        return acting["user"]

    def as_(name: str, user_role: UserRole):
        acting["user"] = UserSchema(
            user_id=str(users.get(name, 0)), tenant_id=tenant, role=user_role, name_ar="u"
        )

    main.app.dependency_overrides[main.get_current_user] = current_user
    out: dict = {}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        ) as client:
            as_("owner", UserRole.OWNER)
            farm = await client.post("/api/v1/farms", json={"name": "مزرعة"})
            out["farm"] = farm.status_code, farm.text[:300]
            as_("manager", UserRole.MANAGER)
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
            out["in_fields"] = await owner.fetchval(
                "SELECT count(*) FROM fields WHERE field_id = $1", field_id
            )
            out["in_field_boundaries"] = await owner.fetchval(
                "SELECT count(*) FROM field_boundaries WHERE field_id = $1", field_id
            )
            as_("manager", UserRole.MANAGER)
            task = await client.post(
                "/api/v1/weather/tasks/from-operation-plan",
                json={"field_id": field_id, "lat": 15.302, "lon": 44.202, "operation": "spraying"},
            )
            out["task"] = task.status_code, task.text[:300]
            out["stored_task_field"] = await owner.fetchval(
                "SELECT field_id FROM field_tasks WHERE tenant_id = $1::uuid"
                " AND source_agent IS NOT NULL",
                tenant,
            )
            out["field_id"] = field_id
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            for table in ("field_tasks", "fields", "farms", "users"):
                await owner.execute(f"DELETE FROM {table} WHERE tenant_id = $1::uuid", tenant)
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()
    return out


def test_the_field_tasks_key_names_the_fields_table_and_checks_new_rows():
    async def target():
        conn = await asyncpg.connect(DSN)
        try:
            row = await conn.fetchrow(
                """SELECT confrelid::regclass::text AS target, convalidated, confdeltype
                     FROM pg_constraint
                    WHERE conrelid = 'public.field_tasks'::regclass AND contype = 'f'
                      AND conname = 'field_tasks_field_id_fkey'"""
            )
            # A new task naming a field that exists only in field_boundaries is refused.
            legacy = f"ft-legacy-{uuid.uuid4().hex[:8]}"
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO field_boundaries (field_id, field_name) VALUES ($1, $1)", legacy
                )
                with pytest.raises(asyncpg.ForeignKeyViolationError):
                    async with conn.transaction():
                        await conn.execute(
                            "INSERT INTO field_tasks (field_id, task_type) VALUES ($1, 'scouting')",
                            legacy,
                        )
                await conn.execute("DELETE FROM field_boundaries WHERE field_id = $1", legacy)
            return row
        finally:
            await conn.close()

    row = asyncio.run(target())
    assert row is not None
    assert (row["target"], row["confdeltype"]) == ("fields", b"c")
    # NOT VALID by design: validation is operator-run (docs/runbooks/validate_not_valid_constraints.md).
    assert row["convalidated"] is False


def test_a_task_on_a_field_created_through_the_api_is_stored(monkeypatch):
    out = asyncio.run(_journey(monkeypatch))
    assert out["farm"][0] == 201, out["farm"]
    assert out["field"][0] == 201, out["field"]
    # The field exists only where the API writes it: the legacy table is not mirrored.
    assert (out["in_fields"], out["in_field_boundaries"]) == (1, 0)
    assert out["task"][0] == 200, out["task"]
    assert '"created":true' in out["task"][1].replace(" ", ""), out["task"]
    assert out["stored_task_field"] == out["field_id"]
