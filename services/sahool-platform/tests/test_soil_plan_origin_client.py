"""Gap P6 — the platform's soil-service client for plan origins fails closed.

Every answer is a verified origin, a typed refusal, or ``SamplingPlanVerificationUnavailable``;
nothing that soil-service did not verify can reach the lab-sample store.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import respx
from api import soil_hydraulic_client as client
from api.routers import internal_service

_BASE = "http://soil.test"
_TENANT = "aaaaaaaa-0000-4000-8000-00000000000a"
_URL = f"{_BASE}/v1/fields/f-1/soil/sampling-plan-copies/ssp-1/origin"
_ORIGIN = {
    "plan_id": "ssp-1",
    "point_id": "ss-1",
    "plan_digest": "a" * 64,
    "verification": "stored_plan",
    "resolved_by": "soil-service",
    "latitude": 16.0,
    "longitude": 44.0,
    "collection": {"latitude": 16.0001, "longitude": 44.0, "deviation_m": 11.1, "on_plan": True},
}


@pytest.fixture(autouse=True)
def _soil_env(monkeypatch):
    monkeypatch.setenv("SOIL_SERVICE_URL", _BASE)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "svc-token")


async def _resolve():
    return await client.resolve_sampling_origin(
        tenant_id=_TENANT,
        field_id="f-1",
        plan_id="ssp-1",
        point_id="ss-1",
        latitude=16.0001,
        longitude=44.0,
        gps_accuracy_m=None,
        deviation_reason=None,
        claimed={"point_id": "ss-1"},
    )


@respx.mock
async def test_a_verified_origin_is_returned_with_the_tenant_header():
    route = respx.post(_URL).mock(return_value=httpx.Response(200, json=_ORIGIN))
    assert await _resolve() == _ORIGIN
    request = route.calls.last.request
    assert request.headers["X-Tenant-Id"] == _TENANT
    assert request.headers["X-Agent-Token"] == "svc-token"


@respx.mock
@pytest.mark.parametrize(
    "code",
    ["sampling_plan_not_found", "sampling_point_not_in_plan", "sampling_origin_out_of_tolerance"],
)
async def test_typed_refusals_are_passed_on(code):
    status = 404 if code == "sampling_plan_not_found" else 422
    respx.post(_URL).mock(return_value=httpx.Response(status, json={"detail": {"code": code}}))
    with pytest.raises(client.SamplingOriginRefused) as refused:
        await _resolve()
    assert refused.value.detail["code"] == code


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"detail": "boom"}),
        httpx.Response(503, json={"detail": "database unavailable"}),
        httpx.Response(
            404, json={"detail": "Not Found"}
        ),  # an older soil-service without the route
        httpx.Response(401, json={"detail": "bad token"}),
        httpx.Response(200, json={**_ORIGIN, "verification": "client_claim"}),
        httpx.Response(200, json={**_ORIGIN, "plan_id": "ssp-other"}),
        httpx.Response(
            200, json={**_ORIGIN, "collection": {**_ORIGIN["collection"], "latitude": 16.6}}
        ),
        httpx.Response(200, text="not json"),
    ],
)
async def test_anything_but_a_verified_answer_is_unavailable(response):
    respx.post(_URL).mock(return_value=response)
    with pytest.raises(client.SamplingPlanVerificationUnavailable):
        await _resolve()


@respx.mock
async def test_an_unreachable_soil_service_is_unavailable():
    respx.post(_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(client.SamplingPlanVerificationUnavailable):
        await _resolve()


async def test_no_service_token_is_unavailable_not_unverified(monkeypatch):
    for name in ("INTERNAL_SERVICE_TOKEN", "SOIL_SERVICE_TOKEN", "SAHOOL_AGENT_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(client.SamplingPlanVerificationUnavailable):
        await _resolve()


def _advice(plans):
    return SimpleNamespace(tenant_id=_TENANT, field_id="f-1", soil_sampling_plans=plans)


@respx.mock
async def test_the_advice_event_hands_plans_to_soil_service():
    route = respx.post(f"{_BASE}/v1/fields/f-1/soil/sampling-plan-copies").mock(
        return_value=httpx.Response(
            201, json={"stored": 1, "unchanged": 0, "conflicting": 0, "skipped": 0}
        )
    )
    receipt = await internal_service._hand_plans_to_soil_service(_advice([{"plan": {}}]))
    assert receipt["stored"] == 1
    assert route.calls.last.request.headers["X-Tenant-Id"] == _TENANT


@respx.mock
async def test_a_failed_hand_off_is_reported_and_no_plan_is_assumed_stored():
    respx.post(f"{_BASE}/v1/fields/f-1/soil/sampling-plan-copies").mock(
        return_value=httpx.Response(503, json={"detail": "database unavailable"})
    )
    receipt = await internal_service._hand_plans_to_soil_service(_advice([{"plan": {}}]))
    assert receipt["stored"] == 0 and "503" in receipt["error"]
    assert await internal_service._hand_plans_to_soil_service(_advice([])) is None
