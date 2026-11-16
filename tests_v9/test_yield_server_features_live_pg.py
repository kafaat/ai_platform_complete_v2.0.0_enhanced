"""W1-08: the yield estimate is built from the server's stored evidence (live PG).

Before W1-08, POST /api/v1/fields/{field_id}/yield-estimate read every feature from the request
body; ``build_features_from_events`` had no caller, so a field whose stored events record pest
alerts and water stress still came back ``unavailable_insufficient_evidence`` (or, before W0-11,
at the full target) when the client sent only the crop.

This file drives the real routes over HTTP into the platform app, against a migrated Postgres
through a NOBYPASSRLS role: tenant A creates a farm, a field and a sown drip season; pest, water
stress and irrigation events for that field are stored in ``events``; tenant B stores a pest event
that names tenant A's field in its payload. Tenant A then asks for the estimate with only the crop
and gets a number below the wheat target whose ``evidence_ids`` name A's stored events and the
weather slice, and never B's event (RLS).

Raster and weather are HTTP services, not part of this database: they are stubbed at the facade
function level (``load_ndvi_points`` / ``load_weather_rain``), never with a fake connection.
Event rows and users are seeded by the schema owner (TEST_DATABASE_ADMIN_URL when set).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
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
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
RING = [[44.300, 15.400], [44.304, 15.400], [44.304, 15.404], [44.300, 15.404], [44.300, 15.400]]
WHEAT_TARGET = 2800


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("fields", "farms", "users", "seasons", "events"):
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

    return main, fields_router


async def _store_event(owner, tenant: str, field_id: str, event_type: str, when, payload=None):
    body = {"field_id": field_id, **(payload or {})}
    return str(
        await owner.fetchval(
            "INSERT INTO events (event_type, entity_type, entity_id, tenant_id, payload, source,"
            " occurred_at) VALUES ($1, 'field', $2, $3::uuid, $4::jsonb, 'web', $5)"
            " RETURNING event_id",
            event_type,
            field_id,
            tenant,
            json.dumps(body),
            when,
        )
    )


async def _journey(monkeypatch) -> dict:
    main, fields_router = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    today = datetime.now(UTC).date()
    sow = today - timedelta(days=40)
    weather_calls: list[tuple[date, date]] = []
    from api import yield_heuristics as ysf

    # Negative control on a tree without W1-08: the facades do not exist, nothing to stub.
    if hasattr(ysf, "collect_server_evidence"):

        async def no_ndvi(_field_id, _tenant_id):
            return []

        async def dry_weather(_location, start, end, _tenant_id):
            weather_calls.append((start, end))
            return [0.0] * ((end - start).days + 1), "weather:snap-live"

        monkeypatch.setattr(ysf, "load_ndvi_points", no_ndvi)
        monkeypatch.setattr(ysf, "load_weather_rain", dry_weather)

    tenants = {"a": str(uuid.uuid4()), "b": str(uuid.uuid4())}
    owner = await asyncpg.connect(ADMIN_DSN)
    app_conn = await asyncpg.connect(DSN)
    try:
        privileged = await app_conn.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
    finally:
        await app_conn.close()
    role = None
    if privileged:
        role = f"ysf_rls_{uuid.uuid4().hex[:10]}"
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
    users = {}
    for key, tenant in tenants.items():
        users[key] = await owner.fetchval(
            "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active)"
            " VALUES ($1, 'x', 'manager', 'manager', $2::uuid, true) RETURNING id",
            f"ysf.{key}.{uuid.uuid4().hex[:8]}@example.org",
            tenant,
        )
    acting = {"user": None}

    def current_user():
        return acting["user"]

    def as_(key: str, user_role: UserRole):
        acting["user"] = UserSchema(
            user_id=str(users[key]), tenant_id=tenants[key], role=user_role, name_ar="u"
        )

    main.app.dependency_overrides[main.get_current_user] = current_user
    out: dict = {"stored": {}, "weather_calls": weather_calls, "today": today, "sow": sow}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        ) as client:
            as_("a", UserRole.OWNER)
            farm = await client.post("/api/v1/farms", json={"name": "مزرعة"})
            out["farm"] = farm.status_code, farm.text[:300]
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
            season = await client.post(
                f"/api/v1/fields/{field_id}/seasons",
                json={
                    "crops": ["wheat"],
                    "irrigation_type": "drip",
                    "sowing_date": sow.isoformat(),
                },
            )
            out["season"] = season.status_code, season.text[:300]

            def at(day: int) -> datetime:
                return datetime(sow.year, sow.month, sow.day, 9, tzinfo=UTC) + timedelta(days=day)

            stored = out["stored"]
            stored["irr1"] = await _store_event(
                owner, tenants["a"], field_id, "operation.irrigation.completed", at(0)
            )
            stored["irr2"] = await _store_event(
                owner, tenants["a"], field_id, "operation.irrigation.completed", at(12)
            )
            stored["pest1"] = await _store_event(
                owner, tenants["a"], field_id, "pest.detected", at(8)
            )
            stored["pest2"] = await _store_event(
                owner, tenants["a"], field_id, "alert.created", at(9), {"alert_type": "pest"}
            )
            stored["moist1"] = await _store_event(
                owner, tenants["a"], field_id, "weather.moisture.low", at(20)
            )
            stored["moist2"] = await _store_event(
                owner, tenants["a"], field_id, "weather.moisture.low", at(25)
            )
            stored["before_season"] = await _store_event(
                owner, tenants["a"], field_id, "pest.detected", at(-30)
            )
            stored["other_tenant"] = await _store_event(
                owner, tenants["b"], field_id, "pest.detected", at(10)
            )

            as_("a", UserRole.VIEWER)
            r = await client.post(
                f"/api/v1/fields/{field_id}/yield-estimate", json={"crop": "wheat"}
            )
            out["estimate"] = r.status_code, r.json() if r.status_code == 200 else r.text[:400]
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            # events is append-only (immutable audit): its rows carry fresh random tenants
            # and are left in place, as every other live test that emits events does.
            for table in ("seasons", "fields", "farms", "users"):
                await owner.execute(
                    f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                    list(tenants.values()),
                )
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()
    return out


def test_stored_pest_and_water_stress_events_give_yield_below_target(monkeypatch):
    out = asyncio.run(_journey(monkeypatch))
    assert out["farm"][0] == 201, f"farm setup failed: {out['farm']}"
    assert out["field"][0] == 201, f"field setup failed: {out['field']}"
    assert out["season"][0] == 201, f"season setup failed: {out['season']}"

    status, body = out["estimate"]
    assert status == 200, f"own field: expected 200, got {status}: {body}"
    assert body.get("yield_status") == "estimated", (
        f"stored pest/water-stress events must give an estimate, not unknown: {body}"
    )
    assert body["estimated_yield_kg_ha"] < WHEAT_TARGET, (
        f"pest alerts and water stress must lower the wheat yield below {WHEAT_TARGET}: {body}"
    )
    ids = set(body.get("evidence_ids") or [])
    stored = out["stored"]
    for key in ("irr1", "irr2", "pest1", "pest2", "moist1", "moist2"):
        assert f"event:{stored[key]}" in ids, f"stored event {key} was used but is not cited: {ids}"
    assert f"event:{stored['before_season']}" not in ids, (
        f"an event before the sowing date is not this season's evidence: {ids}"
    )
    assert f"event:{stored['other_tenant']}" not in ids, (
        f"another tenant's event leaked into the estimate (RLS): {ids}"
    )
    assert "weather:snap-live" in ids, f"the weather slice used for drought is not cited: {ids}"
    sources = body.get("input_sources") or {}
    assert sources.get("pest_alerts") == "server:events", sources
    assert sources.get("moisture_stress_events") == "server:events", sources
    assert sources.get("drought_streak_days") == "server:weather_history", sources
    assert body.get("declared_overrides") == [], (
        f"the request only declared the season's own crop; nothing was overridden: {body}"
    )
    window = body.get("evidence_window") or {}
    assert window.get("start") == out["sow"].isoformat(), window
    assert out["weather_calls"] == [(out["sow"], out["today"] - timedelta(days=1))], (
        f"weather history must cover sowing..yesterday: {out['weather_calls']}"
    )
