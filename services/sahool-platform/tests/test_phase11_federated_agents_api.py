import os

from api.phase11_federated_agents import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

# phase9-12 routers مؤمَّنة بتوكن خدمة على مستوى الراوتر؛ نضبط السرّ ونمرّر الترويسة.
os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-agent-token")


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, headers={"X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"]})


def test_phase11_cycle_endpoint():
    c = client()
    payload = {
        "canonical_field_state": {
            "field_id": "field-api",
            "confidence": 0.8,
            "operational_truths": {
                "water_stress": 0.77,
                "soil_moisture": 0.2,
                "salinity_risk": 0.1,
            },
        },
        "execution_mode": "shadow",
    }
    res = c.post("/v1/phase11/federation/cycle", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["cycle_id"].startswith("fedcycle_")
    assert data["operation_plan"]["dispatch_ready"] is False


def test_phase11_consensus_endpoint():
    c = client()
    proposals = [
        {
            "proposal_id": "p1",
            "agent_role": "water",
            "action": "irrigate",
            "confidence": 0.8,
            "priority": 90,
            "rationale": [],
            "safety_flags": [],
        },
        {
            "proposal_id": "p2",
            "agent_role": "safety",
            "action": "block",
            "confidence": 0.9,
            "priority": 100,
            "rationale": [],
            "safety_flags": ["low_confidence_veto"],
        },
    ]
    res = c.post(
        "/v1/phase11/federation/consensus",
        json={"proposals": proposals, "execution_mode": "autonomous"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "blocked"
