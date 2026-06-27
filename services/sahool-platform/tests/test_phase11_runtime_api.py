import os

from api.phase11_federated_agents import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

# phase9-12 routers مؤمَّنة بتوكن خدمة على مستوى الراوتر؛ نضبط السرّ ونمرّر الترويسة.
os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-agent-token")

app = FastAPI()
app.include_router(router)
client = TestClient(app, headers={"X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"]})


def test_runtime_resolve_endpoint_blocks_conflict():
    payload = {
        "proposals": [
            {"agent_role": "water", "action": "irrigate", "confidence": 0.9, "priority": 80},
            {
                "agent_role": "safety",
                "action": "block",
                "confidence": 0.95,
                "priority": 90,
                "safety_flags": ["unsafe_veto"],
            },
        ],
        "execution_mode": "autonomous",
    }
    response = client.post("/v1/phase11/federation/runtime/resolve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["approval_required"] is True


def test_runtime_authority_endpoint_fail_closed():
    response = client.post(
        "/v1/phase11/federation/runtime/authority-envelope",
        json={
            "cycle": {"cycle_id": "c1", "context": {"field_id": "field-1"}},
            "resolution": {
                "resolution_id": "r1",
                "status": "needs_human_approval",
                "selected_action": "irrigate",
                "approval_required": True,
            },
            "requested_authority": "execution",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["may_execute"] is False
    assert data["allowed_authority"] == "advisory_blocked"


def test_cycle_endpoint_includes_runtime_envelope():
    response = client.post(
        "/v1/phase11/federation/cycle",
        json={
            "canonical_field_state": {
                "field_id": "field-1",
                "truths": {"water_stress": 0.8, "soil_moisture": 0.2},
                "confidence": 0.9,
            },
            "execution_mode": "human_in_loop",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "runtime_resolution" in data
    assert "authority_envelope" in data
    assert data["authority_envelope"]["may_execute"] is False
