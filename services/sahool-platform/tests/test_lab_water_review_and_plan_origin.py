"""Water lab results bind review to explicit ids; a plan point is resolved from a stored copy.

The PostgreSQL behaviour (one stored row after a lost response or concurrent submits, the
revision chain and the publish history) is proved on a disposable database by the branch's
PG proof; these tests pin the handler and resolver contracts without a database.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from api import lab_store
from api.main import get_current_user
from api.routers import soil_sampling as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.ai_agronomist.soil_sampling_planner import plan_copies_for_platform

TENANT = "00000000-0000-0000-0000-000000000001"
SCENE = {"scene_id": "S2A_20260501", "acquisition_date": "2026-05-01"}
POINT = {
    "sample_id": "ss-1-1",
    "zone_id": "Z1",
    "point": {"type": "Point", "coordinates": [44.2, 15.3]},
    "depth_cm": [0, 30],
    "indicators": ["ndvi"],
    "indicator_sources": {"ndvi": SCENE},
}


class PlanConn:
    """The two reads resolve_sampling_origin makes: the stored plan and the raster registry."""

    def __init__(self, points=None, assets=()):
        self.points, self.assets = points, set(assets)

    async def fetchrow(self, query, *args):
        if "soil_sampling_plan_copies" in query:
            return {"sample_points": self.points} if self.points is not None else None
        if "raster_assets" in query:
            return {"ok": 1} if (args[2], str(args[3]), args[4]) in self.assets else None
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        return True


def resolve(conn, *, claimed=None, latitude=15.3, longitude=44.2, reason=None):
    claimed = claimed or {
        "point_id": "ss-1-1",
        "zone_id": "Z1",
        "latitude": 15.3,
        "longitude": 44.2,
        "indicators": ["ndvi"],
        "indicator_sources": {"ndvi": SCENE},
    }
    return asyncio.run(
        lab_store.resolve_sampling_origin(
            conn,
            tenant_id=TENANT,
            field_id="f1",
            plan_id="ssp-1",
            claimed=claimed,
            latitude=latitude,
            longitude=longitude,
            gps_accuracy_m=None,
            deviation_reason=reason,
        )
    )


def test_a_fabricated_plan_is_kept_as_an_unverified_claim():
    origin = resolve(PlanConn(points=None))
    assert origin["verification"] == "unverified"
    assert origin["plan_verification"] == "plan_not_stored"
    assert origin["layer_verification"] == {"ndvi": "unverified"}


def test_a_stored_point_with_a_registered_scene_is_documented():
    origin = resolve(PlanConn([POINT], assets={("S2A_20260501", "2026-05-01", "ndvi")}))
    assert origin["verification"] == "documented"
    assert origin["layer_verification"] == {"ndvi": "verified"}
    assert origin["collection"]["on_plan"] is True
    assert origin["planned_depth_cm"] == [0, 30]


def test_an_unknown_scene_or_an_ndvi_without_scene_is_never_documented():
    unknown = resolve(PlanConn([POINT], assets=()))
    assert unknown["verification"] == "unverified"
    assert unknown["unverified_indicators"] == ["ndvi"]
    bare = dict(POINT, indicator_sources={})
    no_scene = resolve(PlanConn([bare], assets={("S2A_20260501", "2026-05-01", "ndvi")}))
    assert no_scene["verification"] == "unverified"
    assert no_scene["unverified_indicators"] == ["ndvi"]


def test_the_stored_copy_wins_over_the_client_claim():
    claimed = {
        "point_id": "ss-1-1",
        "zone_id": "Z9",
        "latitude": 15.9,
        "longitude": 44.9,
        "indicators": ["ndvi"],
        "indicator_sources": {"ndvi": {"scene_id": "FAKE", "acquisition_date": "2026-01-01"}},
    }
    origin = resolve(
        PlanConn([POINT], assets={("S2A_20260501", "2026-05-01", "ndvi")}), claimed=claimed
    )
    assert (origin["latitude"], origin["longitude"], origin["zone_id"]) == (15.3, 44.2, "Z1")
    assert origin["indicator_sources"] == {"ndvi": SCENE}
    assert origin["client_claim_mismatch"] == [
        "indicator_sources",
        "latitude",
        "longitude",
        "zone_id",
    ]


def test_a_far_collection_point_is_recorded_with_its_deviation_and_reason():
    origin = resolve(
        PlanConn([POINT], assets={("S2A_20260501", "2026-05-01", "ndvi")}),
        latitude=15.3027,
        reason="rock outcrop at the planned point",
    )
    collection = origin["collection"]
    assert collection["on_plan"] is False
    assert 290 < collection["deviation_m"] < 310
    assert collection["deviation_reason"] == "rock outcrop at the planned point"
    assert (collection["latitude"], collection["longitude"]) == (15.3027, 44.2)


def test_a_point_missing_from_the_stored_plan_is_unverified():
    origin = resolve(PlanConn([dict(POINT, sample_id="ss-2-1")]))
    assert origin["plan_verification"] == "point_not_in_plan"
    assert origin["verification"] == "unverified"


def test_planner_calls_become_plan_copies_for_the_same_field_only():
    plan = {"plan_id": "ssp-1", "strata": []}
    calls = [
        {
            "tool": "plan_soil_sampling",
            "data": {"field_id": "f1", "soil_sampling_plan": plan, "sample_points": [POINT]},
        },
        {
            "tool": "plan_soil_sampling",
            "data": {"field_id": "f2", "soil_sampling_plan": plan, "sample_points": [POINT]},
        },
        {
            "tool": "plan_soil_sampling",
            "data": {"field_id": "f1", "soil_sampling_plan": None, "sample_points": []},
        },
        {"tool": "get_alerts", "data": {"field_id": "f1"}},
    ]
    assert plan_copies_for_platform(calls, "f1") == [
        {"field_id": "f1", "plan": plan, "sample_points": [POINT]}
    ]
    assert plan_copies_for_platform(calls, None) == []


def _client(monkeypatch, user_id="reviewer", **store):
    @asynccontextmanager
    async def connection(user):
        yield object()

    monkeypatch.setattr(mod, "tenant_connection", connection)
    for name, fn in store.items():
        monkeypatch.setattr(mod.lab_store, name, fn)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: UserSchema(
        user_id=user_id, tenant_id=TENANT, role=UserRole.MANAGER, name_ar="مراجع"
    )
    return TestClient(app)


def _water_review_store(live_id, sealed):
    sample = {"sample_id": "w-1", "kind": "water", "status": "result_received", "field_id": "f1"}

    async def get_sample(conn, *, tenant_id, sample_id):
        return dict(sample)

    async def has_water_result(conn, *, tenant_id, sample_id, quality):
        return quality == "unreviewed"

    async def water_review_results(conn, tenant_id, sample_id):
        return [{"result_id": live_id, "quality_status": "unreviewed"}]

    async def result_entry_actors(conn, tenant_id, sample_id):
        return {"lab-tech"}

    async def set_status(conn, *, tenant_id, sample_id, status):
        sample["status"] = status
        return dict(sample)

    async def seal_water_review(conn, **kwargs):
        sealed.append(kwargs)

    async def add_custody_event(*args, **kwargs):
        return {}

    return dict(
        get_sample=get_sample,
        has_water_result=has_water_result,
        water_review_results=water_review_results,
        result_entry_actors=result_entry_actors,
        set_status=set_status,
        seal_water_review=seal_water_review,
        add_custody_event=add_custody_event,
    )


@pytest.mark.parametrize("body_ids", [None, "stale"])
def test_water_approval_without_the_shown_ids_is_refused(monkeypatch, body_ids):
    live, sealed = uuid4(), []
    c = _client(monkeypatch, **_water_review_store(live, sealed))
    body = {"target_status": "approved"}
    if body_ids == "stale":
        body["reviewed_result_ids"] = [str(uuid4())]
    response = c.post("/api/v1/lab/samples/w-1/transition", json=body)
    assert response.status_code == 409, response.text
    assert sealed == []


def test_water_approval_seals_exactly_the_named_set(monkeypatch):
    live, sealed = uuid4(), []
    c = _client(monkeypatch, **_water_review_store(live, sealed))
    response = c.post(
        "/api/v1/lab/samples/w-1/transition",
        json={"target_status": "approved", "reviewed_result_ids": [str(live)]},
    )
    assert response.status_code == 200, response.text
    assert sealed[0]["target"] == "approved" and sealed[0]["result_ids"] == [live]
    assert sealed[0]["actor_id"] == "reviewer"


def test_water_submit_maps_store_refusals_and_sends_the_digest(monkeypatch):
    seen = []

    async def record_water_result(conn, **kwargs):
        seen.append(kwargs)
        if kwargs["supersedes"] is None and len(seen) > 1:
            raise lab_store.WaterResultRefused(409, "a correction must name the current result")
        return {"result_id": "r1", **kwargs["analysis"]}

    c = _client(monkeypatch, user_id="lab-tech", record_water_result=record_water_result)
    body = {"sample_id": "w-1", "na": 4, "ca": 3, "mg": 3, "ec_dsm": 0.5}
    first = c.post("/api/v1/lab/water-results", json=body)
    assert first.status_code == 200 and first.json()["result_id"] == "r1"
    again = c.post("/api/v1/lab/water-results", json={**body, "na": 5})
    assert again.status_code == 409
    assert seen[0]["request_digest"] != seen[1]["request_digest"]
    assert "supersedes_result_id" not in seen[0]["payload"]
    corrected = c.post(
        "/api/v1/lab/water-results",
        json={**body, "na": 5, "supersedes_result_id": str(uuid4()), "correction_reason": "typo"},
    )
    assert corrected.status_code == 200
    assert seen[2]["correction_reason"] == "typo"


def test_the_advice_event_stores_the_planner_plans_for_its_field(monkeypatch):
    from api import main
    from api.routers import internal_service

    saved = []

    @asynccontextmanager
    async def connection(actor):
        yield object()

    async def assert_field(conn, field_id):
        return None

    async def emit(*args, **kwargs):
        return True

    async def save(conn, **kwargs):
        saved.append(kwargs)
        return 1

    monkeypatch.setattr(main, "tenant_connection", connection)
    monkeypatch.setattr(main, "_assert_field_in_tenant", assert_field)
    monkeypatch.setattr(main, "_emit_domain_event", emit)
    monkeypatch.setattr(internal_service.lab_store, "save_sampling_plan_copies", save)
    plans = [{"field_id": "f1", "plan": {"plan_id": "ssp-1"}, "sample_points": [POINT]}]
    request = main.InternalAIAdviceEventRequest(
        tenant_id=TENANT, field_id="f1", question="plan sampling", soil_sampling_plans=plans
    )
    reply = asyncio.run(internal_service.internal_ai_advice_event(request, None))
    assert reply["soil_sampling_plans_stored"] == 1
    assert saved == [
        {
            "tenant_id": TENANT,
            "field_id": "f1",
            "plans": plans,
            "source": "ai_agronomist.plan_soil_sampling",
        }
    ]


def test_the_runtime_sends_the_plans_with_the_advice_event(monkeypatch):
    import json

    import httpx

    from services.ai_agronomist import ai_evidence_runtime as runtime

    sent = []
    real = httpx.AsyncClient

    def reply(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"persisted": True})

    monkeypatch.setattr(runtime, "AGENT_TOKEN", "agent-token-for-test")
    monkeypatch.setattr(
        runtime.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(reply), **kw),
    )
    plans = [{"field_id": "f1", "plan": {"plan_id": "ssp-1"}, "sample_points": [POINT]}]
    asyncio.run(
        runtime._record_ai_advice_event(
            tenant_id=TENANT,
            field_id="f1",
            question="q",
            evidence_ids=[],
            confidence=0.0,
            selected_imagery_date=None,
            endpoint_mode="chat",
            soil_sampling_plans=plans,
        )
    )
    assert sent[0]["soil_sampling_plans"] == plans
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    # The plans are collected after the request's own tool calls ran, before the event.
    assert (
        source.index("tool_loop.run_tool_calls")
        < source.index("sampling_plans = plan_copies_for_platform(")
        < source.index("audit_event = await _record_ai_advice_event(")
    )
