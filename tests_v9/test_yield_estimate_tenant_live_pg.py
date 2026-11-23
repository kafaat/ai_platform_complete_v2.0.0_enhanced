"""W0-11: the yield estimate answers only for a field in the caller's tenant (live PG).

POST /api/v1/fields/{field_id}/yield-estimate used to compute an estimate for any field id
(``get_current_user`` only, no ownership check), and a body carrying nothing but the crop came
back with the full target yield because absent inputs were read as zero stress. This file drives
the real routes over HTTP into the platform app, against a migrated Postgres through a
NOBYPASSRLS role: tenant A creates a farm and a field; tenant B asks for that field's estimate
and gets 404 with no number; tenant A with only the crop gets
``unavailable_insufficient_evidence`` and no number; tenant A with declared observations gets an
estimate.

Only the users rows are seeded by the schema owner (TEST_DATABASE_ADMIN_URL when set): accounts are provisioned by the auth service.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

# Switch read before any import (test_certification_switch_precedes_importorskip): on the
# certifying CI step a missing dependency or an unusable database fails the run, not a skip.
_CERTIFICATION_REQUIRED = os.getenv("YIELD_ESTIMATE_TENANT_CERTIFICATION_REQUIRED") == "1"


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
# Users rows are seeded by the schema owner when one is given (the request path still runs
# through DSN, which the CI harness points at a NOBYPASSRLS role).
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
RING = [[44.300, 15.400], [44.304, 15.400], [44.304, 15.404], [44.300, 15.404], [44.300, 15.400]]


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("fields", "farms", "users"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        f"YIELD_ESTIMATE_TENANT_CERTIFICATION_REQUIRED=1 but the live database is unusable: {_WHY}"
    )
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import fields as fields_router

    return main, fields_router


async def _journey(monkeypatch) -> dict:
    main, fields_router = _platform()
    from core.canonical_schemas import UserRole, UserSchema

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
        # DSN bypasses RLS: run the requests under a NOBYPASSRLS role so isolation is measured.
        role = f"ye_rls_{uuid.uuid4().hex[:10]}"
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

    # Creating a field queues Sentinel processing after the response; it calls other services
    # and is not what this file measures.
    async def no_imagery(**_kwargs):
        return None

    monkeypatch.setattr(fields_router, "_kick_imagery_processing", no_imagery)
    users = {}
    for key, tenant in tenants.items():
        users[key] = await owner.fetchval(
            "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active)"
            " VALUES ($1, 'x', 'manager', 'manager', $2::uuid, true) RETURNING id",
            f"ye.{key}.{uuid.uuid4().hex[:8]}@example.org",
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
    out: dict = {}
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
            route = f"/api/v1/fields/{field.json().get('field_id')}/yield-estimate"

            as_("b", UserRole.MANAGER)
            other = await client.post(route, json={"crop": "wheat", "pest_alerts": 0})
            out["other_tenant"] = other.status_code, other.text[:300]

            as_("a", UserRole.VIEWER)
            bare = await client.post(route, json={"crop": "wheat"})
            out["crop_only"] = bare.status_code, bare.json() if bare.status_code == 200 else {}

            observed = await client.post(
                route,
                json={
                    "crop": "wheat",
                    "moisture_stress_events": 0,
                    "drought_streak_days": 0,
                    "pest_alerts": 2,
                },
            )
            out["observed"] = (
                observed.status_code,
                observed.json() if observed.status_code == 200 else {},
            )
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            for table in ("fields", "farms", "users"):
                await owner.execute(
                    f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                    list(tenants.values()),
                )
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()
    return out


def test_yield_estimate_is_tenant_scoped_and_absence_is_not_full_target(monkeypatch):
    out = asyncio.run(_journey(monkeypatch))
    assert out["farm"][0] == 201, f"farm setup failed: {out['farm']}"
    assert out["field"][0] == 201, f"field setup failed: {out['field']}"

    status, text = out["other_tenant"]
    assert status == 404, f"another tenant's field must be 404, got {status}: {text}"
    assert "estimated_yield_kg_ha" not in text, f"no estimate may leak across tenants: {text}"

    status, body = out["crop_only"]
    assert status == 200, f"own field, crop only: expected 200, got {status}"
    assert body.get("estimated_yield_kg_ha") is None, (
        f"crop-only request returned a number instead of unknown: {body}"
    )
    assert body.get("yield_status") == "unavailable_insufficient_evidence", body
    assert body.get("stress_level") == "unknown", body

    status, body = out["observed"]
    assert status == 200, f"own field with observations: expected 200, got {status}"
    assert body.get("yield_status") == "estimated", body
    assert body.get("estimated_yield_kg_ha") == 2520.0, (
        f"2 pest alerts on wheat: 2800 * 0.90 expected, got {body.get('estimated_yield_kg_ha')}"
    )
    assert body.get("missing_inputs") == ["avg_ndvi_growing"], body
