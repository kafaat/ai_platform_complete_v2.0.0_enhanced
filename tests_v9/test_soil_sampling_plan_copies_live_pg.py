"""Gap P6 — soil-service's plan copies on live PostgreSQL, as a NOSUPERUSER/NOBYPASSRLS role.

What is measured, on the migrated schema (not a copy of it):

1. the application role is really restricted, and ``soil_sampling_plan_copies`` has RLS and FORCE;
2. ownership: ``db_ownership.yml`` names soil-service the owner and only writer, and no
   sahool-platform source names the table (the platform reaches it over HTTP only);
3. v273 applied twice more on the migrated database leaves one policy and one trigger;
4. soil-service's store writes and reads its copy under the tenant context; another tenant and
   a connection without context see nothing; a row for another tenant is refused; a stored copy
   cannot be changed, and a different plan under a stored id is reported as a conflict;
5. negative control on the live copy: the 66 km origin is refused, an on-plan one is resolved.

Run: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration <this file>``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.integration, pytest.mark.security]

_CERTIFICATION_REQUIRED = os.getenv("SOIL_PLAN_COPIES_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg is not installed")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""
if not (_ADMIN_DSN and _APP_DSN) and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "SOIL_PLAN_COPIES_CERTIFICATION_REQUIRED=1 without TEST_DATABASE_ADMIN_URL and "
        "TEST_DATABASE_URL: the job claims a certification with no database to certify on."
    )
pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="needs TEST_DATABASE_ADMIN_URL and TEST_DATABASE_URL (live DB, restricted role)",
    )
)

_ROOT = Path(__file__).resolve().parents[1]
_SOIL = _ROOT / "services" / "soil-service"
_MIGRATION = _ROOT / "migrations" / "v273_soil_sampling_plan_copies.sql"
_TABLE = "soil_sampling_plan_copies"
_TENANT_A = "aaaaaaaa-0000-4000-8000-0000000000a6"
_TENANT_B = "bbbbbbbb-0000-4000-8000-0000000000b6"


def _load(name: str):
    """A soil-service module by path, without putting the service directory on sys.path."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SOIL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load("jsonb_values")
store = _load("plan_copy_store")
origin_rules = _load("plan_origin")


def _copy(field_id: str, plan_id: str, lat: float = 16.0):
    item = {
        "field_id": field_id,
        "plan": {"plan_id": plan_id, "strategy": "zones"},
        "sample_points": [
            {
                "sample_id": "ss-1",
                "zone_id": "Z1",
                "point": {"type": "Point", "coordinates": [44.0, lat]},
                "indicators": ["ndvi"],
                "indicator_sources": {
                    "ndvi": {"scene_id": "S2A_20260501", "acquisition_date": "2026-05-01"}
                },
            }
        ],
    }
    copy = origin_rules.normalize_plan_copy(item, field_id)
    assert copy is not None
    return copy


async def _assert_restricted(admin, app) -> None:
    role = await app.fetchval("SELECT current_user")
    flags = await admin.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=$1", role
    )
    assert flags is not None and not flags["rolsuper"] and not flags["rolbypassrls"], (
        f"{role} bypasses RLS, so nothing below would be measured"
    )


@pytest.mark.asyncio
async def test_table_is_owned_by_soil_service_with_forced_rls_and_reapplies_cleanly():
    admin = await asyncpg.connect(_ADMIN_DSN)
    app = await asyncpg.connect(_APP_DSN)
    try:
        await _assert_restricted(admin, app)
        # v273 twice more on the already-migrated database: re-run safe, nothing duplicated.
        sql = _MIGRATION.read_text(encoding="utf-8")
        await admin.execute(sql)
        await admin.execute(sql)
        security = await admin.fetchrow(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=$1::regclass",
            _TABLE,
        )
        assert security["relrowsecurity"] and security["relforcerowsecurity"]
        policies = await admin.fetch(
            "SELECT polname FROM pg_policy WHERE polrelid=$1::regclass", _TABLE
        )
        assert [p["polname"] for p in policies] == ["soil_sampling_plan_copies_tenant"]
        triggers = await admin.fetchval(
            "SELECT count(*) FROM pg_trigger WHERE tgrelid=$1::regclass AND NOT tgisinternal",
            _TABLE,
        )
        assert triggers == 1
    finally:
        await app.close()
        await admin.close()
    ownership = yaml.safe_load((_ROOT / "docs/architecture/db_ownership.yml").read_text("utf-8"))
    entry = ownership["tables"][_TABLE]
    assert entry["owner"] == "soil-service" and entry["writers"] == ["soil-service"]
    platform = _ROOT / "services" / "sahool-platform"
    leaks = [
        p.relative_to(_ROOT).as_posix()
        for p in platform.rglob("*.py")
        if "/tests/" not in p.as_posix() and _TABLE in p.read_text(encoding="utf-8")
    ]
    assert leaks == [], f"the platform must reach {_TABLE} through soil-service only: {leaks}"


@pytest.mark.asyncio
async def test_soil_service_store_isolates_tenants_and_keeps_copies_immutable():
    admin = await asyncpg.connect(_ADMIN_DSN)
    pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=2)
    field_id = f"p6-field-{uuid.uuid4().hex[:10]}"
    plan_id = f"ssp-{uuid.uuid4().hex[:16]}"
    try:
        async with pool.acquire() as app:
            await _assert_restricted(admin, app)
        copy = _copy(field_id, plan_id)
        first = await store.save_plan_copies(pool, tenant_id=_TENANT_A, copies=[copy], source="t")
        again = await store.save_plan_copies(pool, tenant_id=_TENANT_A, copies=[copy], source="t")
        moved = _copy(field_id, plan_id, lat=16.5)  # same id, another plan point
        conflict = await store.save_plan_copies(
            pool, tenant_id=_TENANT_A, copies=[moved], source="t"
        )
        assert (first["stored"], again["unchanged"], conflict["conflicting"]) == (1, 1, 1)

        mine = await store.get_plan_copy(
            pool, tenant_id=_TENANT_A, field_id=field_id, plan_id=plan_id
        )
        assert mine["plan_digest"] == copy["plan_digest"]
        assert mine["sample_points"][0]["point"]["coordinates"] == [44.0, 16.0]
        theirs = await store.get_plan_copy(
            pool, tenant_id=_TENANT_B, field_id=field_id, plan_id=plan_id
        )
        assert theirs is None, "another tenant reads the plan copy"

        # The row exists (the admin sees it), so the zeros below measure the policy.
        assert await admin.fetchval(f"SELECT count(*) FROM {_TABLE} WHERE plan_id=$1", plan_id) == 1
        bare = await asyncpg.connect(_APP_DSN)
        try:
            assert (
                await bare.fetchval(f"SELECT count(*) FROM {_TABLE} WHERE plan_id=$1", plan_id) == 0
            )
            async with bare.transaction():
                await bare.execute("SELECT set_config('app.current_tenant', $1, true)", _TENANT_B)
                with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                    await bare.execute(
                        f"INSERT INTO {_TABLE} (tenant_id, plan_id, field_id, plan, sample_points,"
                        " plan_digest, source) VALUES ($1::uuid,$2,$3,'{}','[{}]',$4,'t')",
                        _TENANT_A,
                        f"{plan_id}-x",
                        field_id,
                        "0" * 64,
                    )
            async with bare.transaction():
                await bare.execute("SELECT set_config('app.current_tenant', $1, true)", _TENANT_A)
                with pytest.raises(asyncpg.exceptions.ObjectNotInPrerequisiteStateError):
                    await bare.execute(
                        f"UPDATE {_TABLE} SET sample_points='[{{}}]' WHERE plan_id=$1", plan_id
                    )
        finally:
            await bare.close()
    finally:
        await admin.execute(f"DELETE FROM {_TABLE} WHERE plan_id=$1", plan_id)
        await pool.close()
        await admin.close()


@pytest.mark.asyncio
async def test_negative_control_the_66_km_origin_is_refused_against_the_live_copy():
    admin = await asyncpg.connect(_ADMIN_DSN)
    pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=2)
    field_id = f"p6-field-{uuid.uuid4().hex[:10]}"
    plan_id = f"ssp-{uuid.uuid4().hex[:16]}"
    try:
        await store.save_plan_copies(
            pool, tenant_id=_TENANT_A, copies=[_copy(field_id, plan_id)], source="t"
        )
        stored = await store.get_plan_copy(
            pool, tenant_id=_TENANT_A, field_id=field_id, plan_id=plan_id
        )

        def resolve(lat, reason=None):
            return origin_rules.resolve_origin(
                plan_id=stored["plan_id"],
                plan_digest_value=stored["plan_digest"],
                sample_points=stored["sample_points"],
                point_id="ss-1",
                latitude=lat,
                longitude=44.0,
                gps_accuracy_m=None,
                deviation_reason=reason,
                claimed={"indicator_sources": {"ndvi": {"scene_id": "INVENTED"}}},
            )

        with pytest.raises(origin_rules.OriginRefused) as refused:
            resolve(16.6)
        assert refused.value.code == "sampling_origin_out_of_tolerance"
        assert 66_000 < refused.value.extra["deviation_m"] < 67_000
        on_plan = resolve(16.0001)
        assert on_plan["collection"]["on_plan"] is True
        assert on_plan["indicator_sources"]["ndvi"]["scene_id"] == "S2A_20260501"
    finally:
        await admin.execute(f"DELETE FROM {_TABLE} WHERE plan_id=$1", plan_id)
        await pool.close()
        await admin.close()
