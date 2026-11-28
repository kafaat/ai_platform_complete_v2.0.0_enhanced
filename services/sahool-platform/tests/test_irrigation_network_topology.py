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
