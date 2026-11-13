"""Water lab review binds to explicit ids; a plan point resolves from the stored copy (live PG).

These replace the connection stand-ins of
services/sahool-platform/tests/test_lab_water_review_and_plan_origin.py (a PlanConn answering
the plan and registry reads, and a tenant_connection that yielded ``object()`` around patched
store functions). The lab routes run over HTTP into the platform app, on a migrated Postgres,
through a NOBYPASSRLS role. Adapted from the delivery's PG proof (v258).

Water results: the same set again replays; a different set without ``supersedes_result_id``
is 409; approval needs the ids the reviewer was shown (absent or stale: 409; the author: 403);
approval seals exactly the named set; a correction is a revision linked by supersedes.

Plan origin: the AI advice event stores the planner's plan copy for its field; a sample that
names a stored point gets the stored position, zone and scene, and a layer is verified only by
a raster_assets row of this tenant and field. A fabricated plan, an unknown scene and an NDVI
without scene stay unverified; a far point records its deviation and reason.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date
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
_TABLES = (
    "lab_samples",
    "water_lab_result_sets",
    "soil_sampling_plan_copies",
    "raster_assets",
    "fields",
)
SCENE = {"scene_id": "S2A_MSIL2A_20260501", "acquisition_date": "2026-05-01"}
POINT = {
    "sample_id": "ss-1-1",
    "zone_id": "Z1",
    "point": {"type": "Point", "coordinates": [44.2, 15.3]},
    "depth_cm": [0, 30],
    "indicators": ["ndvi"],
    "indicator_sources": {"ndvi": SCENE},
}
WATER = {"na": 4, "ca": 3, "mg": 3, "hco3": 1, "co3": 0, "ec_dsm": 0.5, "ph": 7.4}


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in _TABLES:
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
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import api.main as main
    from api.routers import internal_service

    return main, internal_service


async def _scenario(monkeypatch) -> dict:
    main, internal_service = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    tenant = str(uuid.uuid4())
    field = f"lw-field-{uuid.uuid4().hex[:8]}"
    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"lw_rls_{uuid.uuid4().hex[:10]}"
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
    await owner.execute(
        "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)", field, tenant
    )
    acting = {"user": None}
    main.app.dependency_overrides[main.get_current_user] = lambda: acting["user"]
    out: dict = {}

    async def rows(sample_id):
        return await owner.fetchval(
            "SELECT count(*) FROM water_lab_result_sets WHERE sample_id=$1", sample_id
        )

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        ) as client:

            async def post(path, body, actor="lab-tech"):
                acting["user"] = UserSchema(
                    user_id=actor, tenant_id=tenant, role=UserRole.MANAGER, name_ar="مختبر"
                )
                return await client.post(f"/api/v1/lab/{path}", json=body)

            # ── water results and review ────────────────────────────────────────
            created = await post(
                "samples",
                {
                    "field_id": field,
                    "kind": "water",
                    "latitude": 15.3,
                    "longitude": 44.2,
                    "source": "well",
                },
            )
            assert created.status_code == 200, created.text
            sid = created.json()["sample_id"]
            first = await post("water-results", {"sample_id": sid, **WATER})
            assert first.status_code == 200, first.text
            rid = first.json()["result_id"]
            again = await post("water-results", {"sample_id": sid, **WATER})
            out["replay"] = again.status_code, again.json().get("result_id") == rid
            other = await post("water-results", {"sample_id": sid, **WATER, "na": 5})
            out["other_body"] = other.status_code, await rows(sid)
            transition = f"samples/{sid}/transition"
            out["approve_without_ids"] = (
                await post(transition, {"target_status": "approved"}, actor="reviewer")
            ).status_code
            out["approve_stale_ids"] = (
                await post(
                    transition,
                    {"target_status": "approved", "reviewed_result_ids": [str(uuid.uuid4())]},
                    actor="reviewer",
                )
            ).status_code
            out["approve_by_author"] = (
                await post(transition, {"target_status": "approved", "reviewed_result_ids": [rid]})
            ).status_code
            approved = await post(
                transition,
                {"target_status": "approved", "reviewed_result_ids": [rid]},
                actor="reviewer",
            )
            out["approve_named"] = approved.status_code
            sealed = await owner.fetchrow(
                "SELECT quality_status, approved_by FROM water_lab_result_sets"
                " WHERE result_set_id=$1::uuid",
                rid,
            )
            out["sealed"] = sealed["quality_status"], sealed["approved_by"]
            corrected = await post(
                "water-results",
                {
                    "sample_id": sid,
                    **WATER,
                    "na": 5,
                    "supersedes_result_id": rid,
                    "correction_reason": "dilution error",
                },
            )
            out["correction"] = (
                corrected.status_code,
                corrected.json().get("supersedes_result_id") == rid,
                await rows(sid),
            )

            # ── plan copy stored by the advice event, origin resolved from it ──────
            unknown = {
                **POINT,
                "sample_id": "ss-2-1",
                "indicator_sources": {
                    "ndvi": {"scene_id": "S2_NOT_REGISTERED", "acquisition_date": "2026-05-01"}
                },
            }
            bare = {**POINT, "sample_id": "ss-3-1", "indicator_sources": {}}
            plans = [
                {
                    "field_id": field,
                    "plan": {"plan_id": "ssp-real"},
                    "sample_points": [POINT, unknown, bare],
                }
            ]
            advice = await internal_service.internal_ai_advice_event(
                main.InternalAIAdviceEventRequest(
                    tenant_id=tenant, field_id=field, question="plan", soil_sampling_plans=plans
                ),
                None,
            )
            out["plans_stored"] = advice["soil_sampling_plans_stored"]
            out["copy_source"] = await owner.fetchval(
                "SELECT source FROM soil_sampling_plan_copies"
                " WHERE tenant_id=$1::uuid AND plan_id='ssp-real'",
                tenant,
            )
            await owner.execute(
                """INSERT INTO raster_assets (field_id, tenant_id, scene_id, acquisition_date,
                                              index_name, cog_uri)
                   VALUES ($1, $2::uuid, $3, $4, 'ndvi', 's3://cog/ndvi.tif')""",
                field,
                tenant,
                SCENE["scene_id"],
                date.fromisoformat(SCENE["acquisition_date"]),
            )
            claim = {
                "point_id": "ss-1-1",
                "zone_id": "Z1",
                "latitude": 15.3,
                "longitude": 44.2,
                "indicators": ["ndvi"],
                "indicator_sources": {"ndvi": SCENE},
            }

            def soil(plan_id, origin, lat=15.3, **extra):
                return {
                    "field_id": field,
                    "kind": "soil",
                    "latitude": lat,
                    "longitude": 44.2,
                    "depth_cm_from": 0,
                    "depth_cm_to": 30,
                    "sampling_plan_id": plan_id,
                    "sampling_origin": origin,
                    **extra,
                }

            cases = {
                "on_plan": soil("ssp-real", claim, lat=15.30003),
                "deviation": soil("ssp-real", claim, lat=15.3027, deviation_reason="rock outcrop"),
                "fabricated_plan": soil("ssp-fabricated", {**claim, "latitude": 15.9}),
                "unknown_scene": soil("ssp-real", {**claim, "point_id": "ss-2-1"}),
                "ndvi_without_scene": soil(
                    "ssp-real", {**claim, "point_id": "ss-3-1", "indicator_sources": {}}
                ),
                "claim_differs": soil(
                    "ssp-real",
                    {
                        **claim,
                        "zone_id": "Z9",
                        "latitude": 15.5,
                        "longitude": 44.9,
                        "indicator_sources": {
                            "ndvi": {"scene_id": "FAKE", "acquisition_date": "2026-01-01"}
                        },
                    },
                    lat=15.5,
                ),
            }
            origins = {}
            for label, body in cases.items():
                r = await post("samples", body)
                assert r.status_code == 200, (label, r.text)
                stored = await owner.fetchval(
                    "SELECT sampling_origin FROM lab_samples WHERE sample_id=$1",
                    r.json()["sample_id"],
                )
                origins[label] = json.loads(stored) if isinstance(stored, str) else stored
            out["origins"] = origins
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            if await owner.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"):
                async with owner.transaction():
                    await owner.execute("SET LOCAL session_replication_role = replica")
                    for table in (
                        "lab_sample_custody_events",
                        "water_lab_result_sets",
                        "lab_samples",
                        "soil_sampling_plan_copies",
                        "raster_assets",
                        "fields",
                    ):
                        await owner.execute(
                            f"DELETE FROM {table} WHERE tenant_id = $1::uuid", tenant
                        )
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()
    return out


@pytest.fixture(scope="module")
def scenario():
    mp = pytest.MonkeyPatch()
    try:
        yield asyncio.run(_scenario(mp))
    finally:
        mp.undo()


def test_the_same_set_replays_and_another_set_needs_supersedes(scenario):
    assert scenario["replay"] == (200, True)
    assert scenario["other_body"] == (409, 1)


def test_water_approval_without_the_shown_ids_is_refused(scenario):
    assert scenario["approve_without_ids"] == 409
    assert scenario["approve_stale_ids"] == 409
    assert scenario["approve_by_author"] == 403


def test_water_approval_seals_exactly_the_named_set(scenario):
    assert scenario["approve_named"] == 200
    assert scenario["sealed"] == ("approved", "reviewer")


def test_a_correction_is_a_linked_revision(scenario):
    assert scenario["correction"] == (200, True, 2)


def test_the_advice_event_stores_the_planner_plan_for_its_field(scenario):
    assert scenario["plans_stored"] == 1
    assert scenario["copy_source"] == "ai_agronomist.plan_soil_sampling"


def test_a_stored_point_with_a_registered_scene_is_documented(scenario):
    origin = scenario["origins"]["on_plan"]
    assert origin["verification"] == "documented"
    assert origin["layer_verification"] == {"ndvi": "verified"}
    assert origin["collection"]["on_plan"] is True
    assert origin["planned_depth_cm"] == [0, 30]


def test_a_far_collection_point_records_its_deviation_and_reason(scenario):
    collection = scenario["origins"]["deviation"]["collection"]
    assert collection["on_plan"] is False
    assert 290 < collection["deviation_m"] < 310
    assert collection["deviation_reason"] == "rock outcrop"


def test_a_fabricated_plan_an_unknown_scene_or_a_bare_ndvi_is_never_documented(scenario):
    origins = scenario["origins"]
    assert origins["fabricated_plan"]["plan_verification"] == "plan_not_stored"
    for label in ("fabricated_plan", "unknown_scene", "ndvi_without_scene"):
        assert origins[label]["verification"] == "unverified", label
    assert origins["unknown_scene"]["unverified_indicators"] == ["ndvi"]
    assert origins["ndvi_without_scene"]["unverified_indicators"] == ["ndvi"]


def test_the_stored_copy_wins_over_the_client_claim(scenario):
    origin = scenario["origins"]["claim_differs"]
    assert (origin["latitude"], origin["longitude"], origin["zone_id"]) == (15.3, 44.2, "Z1")
    assert origin["indicator_sources"] == {"ndvi": SCENE}
    assert origin["client_claim_mismatch"] == [
        "indicator_sources",
        "latitude",
        "longitude",
        "zone_id",
    ]
