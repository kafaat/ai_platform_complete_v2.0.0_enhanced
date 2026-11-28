"""Reject ambiguous request topology before invoking the irrigation network screen."""

import pytest
from api.main import UserSchema, get_current_user
from api.routers import irrigation_network as network
from fastapi import FastAPI
from fastapi.testclient import TestClient

URL = "/api/v1/irrigation/network/feasibility"


@pytest.fixture
def boundary(monkeypatch):
    monkeypatch.setenv("FEATURE_IRRIGATION_NETWORK", "1")
    app = FastAPI()
    app.include_router(network.router)
    app.dependency_overrides[get_current_user] = lambda: UserSchema(
        user_id="42", tenant_id="tenant-a", role="owner", name_ar="اختبار"
    )
    calls = []

    def compute(nodes, edges):
        calls.append((nodes, edges))
        return {"overall_feasible": True}

    monkeypatch.setattr(network, "check_network_feasibility", compute)
    return TestClient(app), calls


def _payload():
    return {
        "nodes": [{"node_id": "well", "kind": "well"}, {"node_id": "zone", "kind": "zone"}],
        "edges": [{"from_id": "well", "to_id": "zone"}],
    }


@pytest.mark.parametrize("fault", ["duplicate", "blank", "missing_from", "missing_to"])
def test_invalid_topology_never_reaches_engine(boundary, fault):
    client, calls = boundary
    payload = _payload()
    if fault == "duplicate":
        payload["nodes"].append({"node_id": "well", "kind": "pump"})
    elif fault == "blank":
        payload["nodes"].append({"node_id": "  ", "kind": "pump"})
    elif fault == "missing_from":
        payload["edges"][0]["from_id"] = "missing"
    else:
        payload["edges"][0]["to_id"] = "missing"
    response = client.post(URL, json=payload)
    assert response.status_code == 422
    assert not calls


def test_valid_topology_reaches_engine_with_authenticated_tenant(boundary):
    client, calls = boundary
    response = client.post(URL, json=_payload())
    assert response.status_code == 200
    assert response.json() == {"overall_feasible": True, "tenant_id": "tenant-a"}
    assert len(calls) == 1
    nodes, edges = calls[0]
    assert [node.node_id for node in nodes] == ["well", "zone"]
    assert [(edge.from_id, edge.to_id) for edge in edges] == [("well", "zone")]


def test_disabled_feature_still_returns_404(boundary, monkeypatch):
    client, calls = boundary
    monkeypatch.delenv("FEATURE_IRRIGATION_NETWORK")
    response = client.post(URL, json=_payload())
    assert response.status_code == 404
    assert not calls


@pytest.mark.parametrize(
    ("capacity", "booster_pressure", "expected_a", "expected_b"),
    [
        (3500, 1.5, "infeasible", "feasible"),
        (3500, None, "feasible_unverified", "feasible"),
        (3500, 4.0, "feasible", "feasible"),
        (2500, 4.0, "infeasible", "infeasible"),
    ],
)
def test_synthetic_two_pivots_http_real_screen(
    monkeypatch, capacity, booster_pressure, expected_a, expected_b
):
    # Synthetic 180 ha farm, two 50 ha pivots; 80 ha not assigned demand.
    # One selected well supplies both pivots; five listed wells are not connected
    # in this test window. This is NOT a shared-aquifer allocation or EPANET solve.
    monkeypatch.setenv("FEATURE_IRRIGATION_NETWORK", "1")
    app = FastAPI()
    app.include_router(network.router)
    app.dependency_overrides[get_current_user] = lambda: UserSchema(
        user_id="42", tenant_id="tenant-a", role="owner", name_ar="اختبار"
    )
    area_ha, pivot_ha, depth_mm = 180, 50, 3
    assert area_ha - 2 * pivot_ha == 80
    demand = pivot_ha * depth_mm * 10  # m3 per pivot in this synthetic window
    nodes = [
        {"node_id": "w1", "kind": "well", "capacity_m3": capacity},
        *[{"node_id": f"w{i}", "kind": "well"} for i in range(2, 7)],
        {
            "node_id": "pump",
            "kind": "pump",
            "max_pressure_bar": 5.0,
            "max_throughput_m3": 4000,
        },
        {
            "node_id": "booster-a",
            "kind": "pump",
            "max_pressure_bar": booster_pressure,
            "max_throughput_m3": 2000,
        },
        {"node_id": "a", "kind": "zone", "demand_m3": demand, "min_pressure_bar": 3.0},
        {"node_id": "b", "kind": "zone", "demand_m3": demand, "min_pressure_bar": 3.0},
    ]
    edges = [
        {"from_id": u, "to_id": v}
        for u, v in [("w1", "pump"), ("pump", "booster-a"), ("booster-a", "a"), ("pump", "b")]
    ]
    # Real route and computation; only authentication is overridden.
    with TestClient(app) as client:
        response = client.post(URL, json={"nodes": nodes, "edges": edges})
    assert response.status_code == 200
    result = response.json()
    assert result["tenant_id"] == "tenant-a"
    assert result["zone_count"] == 2
    zones = {z["zone_id"]: z for z in result["zones"]}
    assert zones["a"]["status"] == expected_a
    assert zones["b"]["status"] == expected_b
    assert zones["a"]["path"] == ["a", "booster-a", "pump", "w1"]
    assert zones["b"]["path"] == ["b", "pump", "w1"]
    assert result["overall_feasible"] == ("infeasible" not in (expected_a, expected_b))
    wells = {w["well_id"]: w for w in result["wells"]}
    assert wells["w1"]["load_m3"] == 3000
    assert wells["w1"]["over_capacity"] == (capacity < 3000)
    assert all(wells[f"w{i}"]["load_m3"] == 0 for i in range(2, 7))
    assert result["thresholds_estimated"] is True
    assert result["calibrated"] == "not_applicable"
