"""Gap P6 — plan-point origins are resolved by soil-service from its stored plan copy.

Pure resolution (``plan_origin``) and the route mapping (``routers/plan_copies``). The table's
RLS, ownership and re-applied migration are proven on live PostgreSQL in
``tests_v9/test_soil_sampling_plan_copies_live_pg.py``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (HERE, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import plan_origin  # noqa: E402
from plan_origin import OriginRefused, normalize_plan_copy, resolve_origin  # noqa: E402

pytestmark = pytest.mark.unit

_TENANT_A = "aaaaaaaa-0000-4000-8000-00000000000a"
_TENANT_B = "bbbbbbbb-0000-4000-8000-00000000000b"
_PLANNED = (16.0, 44.0)  # latitude, longitude of the stored plan point
_SCENE = {"scene_id": "S2A_20260501", "acquisition_date": "2026-05-01"}


def _point(sample_id="ss-1", lat=_PLANNED[0], lon=_PLANNED[1]):
    return {
        "sample_id": sample_id,
        "zone_id": "Z1",
        "location_id": "core-1",
        "sampling_purpose": "fertility",
        "composite": True,
        "point": {"type": "Point", "coordinates": [lon, lat]},
        "depth_cm": [0, 30],
        "indicators": ["ndvi"],
        "indicator_sources": {"ndvi": dict(_SCENE)},
    }


def _resolve(lat, lon, *, gps=None, reason=None, point_id="ss-1", claimed=None):
    return resolve_origin(
        plan_id="ssp-1",
        plan_digest_value="d" * 64,
        sample_points=[_point(), _point("ss-2", 16.001, 44.001)],
        point_id=point_id,
        latitude=lat,
        longitude=lon,
        gps_accuracy_m=gps,
        deviation_reason=reason,
        claimed=claimed,
    )


def test_in_tolerance_collection_is_on_plan_and_planned_fields_come_from_the_copy():
    origin = _resolve(16.0001, 44.0001)  # about 15 m from the planned point
    assert origin["verification"] == "stored_plan" and origin["resolved_by"] == "soil-service"
    assert (origin["latitude"], origin["longitude"]) == _PLANNED
    assert origin["zone_id"] == "Z1" and origin["planned_depth_cm"] == [0.0, 30.0]
    assert origin["indicator_sources"] == {"ndvi": _SCENE}
    assert origin["collection"]["on_plan"] is True
    assert origin["collection"]["deviation_m"] < origin["collection"]["tolerance_m"] == 30.0
    assert origin["plan_id"] == "ssp-1" and origin["plan_digest"] == "d" * 64


def test_out_of_tolerance_without_a_reason_is_refused_with_the_measured_distance():
    with pytest.raises(OriginRefused) as refused:
        _resolve(16.6, 44.0)  # about 66.7 km north of the planned point
    assert refused.value.code == "sampling_origin_out_of_tolerance"
    assert refused.value.status == 422
    assert 66_000 < refused.value.extra["deviation_m"] < 67_000
    with pytest.raises(OriginRefused):
        _resolve(16.6, 44.0, reason="  ")  # a blank reason is no reason


def test_out_of_tolerance_with_a_reason_is_recorded_off_plan_with_the_reason():
    origin = _resolve(16.0009, 44.0, reason="rock outcrop at the planned point")
    collection = origin["collection"]
    assert collection["on_plan"] is False
    assert 95 < collection["deviation_m"] < 105
    assert collection["deviation_reason"] == "rock outcrop at the planned point"
    assert (collection["latitude"], collection["longitude"]) == (16.0009, 44.0)


def test_reported_gps_accuracy_cannot_widen_the_tolerance_without_limit():
    # About 39 m: outside the 30 m base tolerance, inside 30 m + 12 m reported GPS accuracy.
    with pytest.raises(OriginRefused):
        _resolve(16.00035, 44.0)
    origin = _resolve(16.00035, 44.0, gps=12.0)
    assert origin["collection"]["on_plan"] is True
    assert origin["collection"]["tolerance_m"] == 42.0
    assert plan_origin.tolerance_m(1e9) == plan_origin.ON_PLAN_TOLERANCE_M + 30.0
    with pytest.raises(OriginRefused):
        _resolve(16.6, 44.0, gps=100_000.0)


def test_point_not_in_the_stored_plan_is_refused():
    with pytest.raises(OriginRefused) as refused:
        _resolve(16.0, 44.0, point_id="ss-invented")
    assert refused.value.code == "sampling_point_not_in_plan"


def test_invented_scene_and_zone_in_the_claim_are_listed_and_never_recorded():
    claimed = {
        "point_id": "ss-1",
        "zone_id": "Z9",
        "latitude": 16.6,
        "longitude": 44.0,
        "indicators": ["ndvi"],
        "indicator_sources": {"ndvi": {"scene_id": "INVENTED", "acquisition_date": "2026-01-01"}},
    }
    origin = _resolve(16.0, 44.0, claimed=claimed)
    assert origin["indicator_sources"] == {"ndvi": _SCENE}
    assert origin["zone_id"] == "Z1" and origin["latitude"] == _PLANNED[0]
    assert origin["client_claim_mismatch"] == ["indicator_sources", "latitude", "zone_id"]


def test_only_well_formed_plans_of_the_same_field_become_copies():
    good = {"field_id": "f-1", "plan": {"plan_id": "ssp-1"}, "sample_points": [_point()]}
    copy = normalize_plan_copy(good, "f-1")
    assert copy["plan_id"] == "ssp-1" and len(copy["plan_digest"]) == 64
    assert normalize_plan_copy(good, "f-other") is None
    no_position = {**good, "sample_points": [{**_point(), "point": {"coordinates": [44.0]}}]}
    assert normalize_plan_copy(no_position, "f-1") is None
    duplicate_ids = {**good, "sample_points": [_point(), _point()]}
    assert normalize_plan_copy(duplicate_ids, "f-1") is None
    assert normalize_plan_copy({**good, "plan": {"plan_id": ""}}, "f-1") is None


# ── route mapping ───────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def loaded_main():
    os.environ["SAHOOL_AGENT_TOKEN"] = "plan-origin-agent-token"
    for name in [m for m in sys.modules if m == "routers" or m.startswith("routers.")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location("main", HERE / "main.py")
    main = importlib.util.module_from_spec(spec)
    sys.modules["main"] = main
    assert spec.loader is not None
    spec.loader.exec_module(main)
    return main


@pytest.fixture
def client(monkeypatch, loaded_main):
    import plan_copy_store

    # Copies keyed by tenant, field and plan, as the table's primary key and policy key them.
    stored = {
        (_TENANT_A, "f-1", "ssp-1"): {
            "plan_id": "ssp-1",
            "field_id": "f-1",
            "plan_digest": "e" * 64,
            "sample_points": [_point()],
        }
    }

    async def get_plan_copy(pool, *, tenant_id, field_id, plan_id):
        return stored.get((tenant_id, field_id, plan_id))

    monkeypatch.setattr(loaded_main, "_pool", object())
    monkeypatch.setattr(plan_copy_store, "get_plan_copy", get_plan_copy)
    return TestClient(loaded_main.app, headers={"X-Agent-Token": "plan-origin-agent-token"})


def _origin(client, tenant, plan_id="ssp-1", **body):
    return client.post(
        f"/v1/fields/f-1/soil/sampling-plan-copies/{plan_id}/origin",
        json={"point_id": "ss-1", "latitude": 16.0, "longitude": 44.0, **body},
        headers={"X-Tenant-Id": tenant},
    )


def test_route_resolves_a_stored_plan_point(client):
    response = _origin(client, _TENANT_A)
    assert response.status_code == 200, response.text
    assert response.json()["verification"] == "stored_plan"


def test_route_refuses_unknown_and_other_tenant_plans_alike(client):
    unknown = _origin(client, _TENANT_A, plan_id="ssp-never-stored")
    other_tenant = _origin(client, _TENANT_B)
    for response in (unknown, other_tenant):
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "sampling_plan_not_found"


def test_route_refuses_out_of_tolerance_without_reason(client):
    response = _origin(client, _TENANT_A, latitude=16.6)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "sampling_origin_out_of_tolerance"


def test_route_requires_the_service_token_and_a_tenant_uuid(client):
    no_token = client.post(
        "/v1/fields/f-1/soil/sampling-plan-copies/ssp-1/origin",
        json={"point_id": "ss-1", "latitude": 16.0, "longitude": 44.0},
        headers={"X-Agent-Token": "wrong", "X-Tenant-Id": _TENANT_A},
    )
    assert no_token.status_code == 401
    assert _origin(client, "not-a-uuid").status_code == 400
