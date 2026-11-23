"""W1-08: the yield estimate is built from the server's stored evidence (live PG).

Before W1-08, POST /api/v1/fields/{field_id}/yield-estimate read every feature from the request
body; ``build_features_from_events`` had no caller, so a field whose stored events record pest
alerts and water stress still came back ``unavailable_insufficient_evidence`` (or, before W0-11,
at the full target) when the client sent only the crop.

This file drives the real routes over HTTP into the platform app, against a migrated Postgres
through a NOBYPASSRLS role, and every piece of evidence comes from a route that produces it in
production: tenant A creates a farm, a field and a sown drip season; records irrigation through
``POST /fields/{id}/activities`` (with ``performed_on`` dates, one of them a pre-sowing
fertilisation recorded today); raises ``low_moisture`` alerts through ``POST /api/v1/alerts``;
and drops pest and disease scouting pins through ``POST /fields/{id}/pins`` (the only pest
producer in the schema; nothing emits ``pest.*`` events or a pest alert type). Tenant B's
``alert.created`` row naming A's field is seeded by the schema owner. Tenant A then asks for the
estimate with only the crop and gets a number below the wheat target whose ``evidence_ids`` name
A's activity events, alert events, scouting pins and the weather slice, never the pre-sowing
fertilisation (windowed on ``performed_on``) and never B's event (RLS).

Raster and weather are HTTP services, not part of this database: they are stubbed at the facade
function level (``load_ndvi_points`` / ``load_weather_rain``), never with a fake connection.
Users and tenant B's event are seeded by the schema owner (TEST_DATABASE_ADMIN_URL when set).
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

# Switch read before any import (test_certification_switch_precedes_importorskip): on the
# certifying CI step a missing dependency or an unusable database fails the run, not a skip.
_CERTIFICATION_REQUIRED = os.getenv("YIELD_SERVER_FEATURES_CERTIFICATION_REQUIRED") == "1"


def _require(module: str):
    """Import ``module``; under the certification switch a missing one fails the run."""
    if _CERTIFICATION_REQUIRED:
        return importlib.import_module(module)
    return pytest.importorskip(module)


asyncpg = _require("asyncpg")
httpx = _require("httpx")
_require("fastapi")

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
        for table in (
            "fields",
            "farms",
            "users",
            "seasons",
            "events",
            "activities",
            "alerts",
            "scouting_pins",
        ):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        f"YIELD_SERVER_FEATURES_CERTIFICATION_REQUIRED=1 but the live database is unusable: {_WHY}"
    )
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
    # Not part of what this proves: the per-client minute window is shared by every test in the
    # process, so the suite before this one must not decide its setup (as test_farm_access_scope_live_pg).
    monkeypatch.setattr(main, "_RATE_LIMIT_PER_MIN", 0, raising=False)

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

            stored = out["stored"]
            setup = out["setup"] = []

            async def activity(key: str, activity_type: str, performed_on: date):
                r = await client.post(
                    f"/api/v1/fields/{field_id}/activities",
                    json={"activity_type": activity_type, "performed_on": performed_on.isoformat()},
                )
                setup.append((key, r.status_code, r.text[:200]))
                stored[key] = await owner.fetchval(
                    "SELECT event_id::text FROM events WHERE entity_id = $1",
                    r.json().get("activity_id"),
                )

            async def alert(key: str):
                r = await client.post(
                    "/api/v1/alerts",
                    json={
                        "alert_type": "low_moisture",
                        "severity": "warning",
                        "field_id": field_id,
                    },
                )
                setup.append((key, r.status_code, r.text[:200]))
                stored[key] = await owner.fetchval(
                    "SELECT event_id::text FROM events WHERE entity_id = $1",
                    r.json().get("alert_id"),
                )

            async def pin(key: str, category: str):
                pin_id = f"pin-{uuid.uuid4().hex[:10]}"
                r = await client.post(
                    f"/api/v1/fields/{field_id}/pins",
                    json={
                        "pin_id": pin_id,
                        "field_id": field_id,
                        "lat": 15.402,
                        "lng": 44.302,
                        "issue_category": category,
                        "severity": "high",
                        "location_source": "gps",
                        "accuracy_m": 5,
                    },
                )
                setup.append((key, r.status_code, r.text[:200]))
                persisted = r.status_code == 200 and r.json().get("persisted") is True
                stored[key] = pin_id if persisted else None

            await activity("irr1", "irrigation", sow)
            await activity("irr2", "irrigation", sow + timedelta(days=12))
            # Performed before sowing, recorded today: its occurred_at is inside the season.
            await activity("before_season", "fertilization", sow - timedelta(days=10))
            await alert("moist1")
            await alert("moist2")
            await pin("pest1", "pest")
            await pin("pest2", "disease")
            await pin("weed", "weed")
            stored["other_tenant"] = await _store_event(
                owner,
                tenants["b"],
                field_id,
                "alert.created",
                datetime.now(UTC),
                {"alert_type": "low_moisture"},
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
            for table in (
                "scouting_pins",
                "activities",
                "alerts",
                "seasons",
                "fields",
                "farms",
                "users",
            ):
                await owner.execute(
                    f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                    list(tenants.values()),
                )
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()
    return out


def test_scouted_pests_and_water_stress_alerts_give_yield_below_target(monkeypatch):
    out = asyncio.run(_journey(monkeypatch))
    assert out["farm"][0] == 201, f"farm setup failed: {out['farm']}"
    assert out["field"][0] == 201, f"field setup failed: {out['field']}"
    assert out["season"][0] == 201, f"season setup failed: {out['season']}"
    for key, code, text in out["setup"]:
        assert code in (200, 201), f"evidence setup {key} failed: {code} {text}"
    stored = out["stored"]
    for key in ("irr1", "irr2", "before_season", "moist1", "moist2", "pest1", "pest2", "weed"):
        assert stored.get(key), f"route did not produce stored evidence for {key}: {stored}"

    status, body = out["estimate"]
    assert status == 200, f"own field: expected 200, got {status}: {body}"
    assert body.get("yield_status") == "estimated", (
        f"stored pest/water-stress events must give an estimate, not unknown: {body}"
    )
    assert body["estimated_yield_kg_ha"] < WHEAT_TARGET, (
        f"pest alerts and water stress must lower the wheat yield below {WHEAT_TARGET}: {body}"
    )
    ids = set(body.get("evidence_ids") or [])
    for key in ("irr1", "irr2", "moist1", "moist2"):
        assert f"event:{stored[key]}" in ids, f"stored event {key} was used but is not cited: {ids}"
    for key in ("pest1", "pest2"):
        assert f"scouting_pin:{stored[key]}" in ids, f"scouted {key} was used but not cited: {ids}"
    assert f"scouting_pin:{stored['weed']}" not in ids, f"a weed pin is not pest evidence: {ids}"
    assert f"event:{stored['before_season']}" not in ids, (
        f"an activity performed before sowing is not this season's evidence: {ids}"
    )
    assert f"event:{stored['other_tenant']}" not in ids, (
        f"another tenant's event leaked into the estimate (RLS): {ids}"
    )
    assert "weather:snap-live" in ids, f"the weather slice used for rain is not cited: {ids}"
    sources = body.get("input_sources") or {}
    assert sources.get("pest_alerts") == "server:scouting_pins", sources
    assert sources.get("fertilizer_applications") == "unknown", (
        f"the only fertilisation was performed before sowing; none is this season's: {sources}"
    )
    assert sources.get("moisture_stress_events") == "server:events", sources
    assert sources.get("rain_events") == "server:weather_history", sources
    # A drip field's irrigation log does not observe the days it was not irrigated, so the
    # weather alone cannot measure its drought: unknown, not a fabricated dry spell.
    assert sources.get("drought_streak_days") == "unknown", sources
    assert body.get("declared_overrides") == [], (
        f"the request only declared the season's own crop; nothing was overridden: {body}"
    )
    window = body.get("evidence_window") or {}
    assert window.get("start") == out["sow"].isoformat(), window
    assert out["weather_calls"] == [(out["sow"], out["today"] - timedelta(days=1))], (
        f"weather history must cover sowing..yesterday: {out['weather_calls']}"
    )
