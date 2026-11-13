"""Water lab results bind review to explicit ids; a plan point is resolved from a stored copy.

The behaviour that depends on the tables (water result replay and revisions, review bound to
the shown ids, the plan copy stored by the advice event, the origin resolved from it and the
raster registry) runs on a migrated Postgres in
tests_v9/test_lab_water_review_and_plan_origin_live_pg.py. What stays here needs no database:
which planner calls become plan copies, and that the runtime sends them with the advice event.
"""

import asyncio
from pathlib import Path

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
