from api.phase9_autonomous_farm_os import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_phase9_plan_api_blocks_shadow_mode():
    c = _client()
    res = c.post(
        "/v1/phase9/autonomy/plan",
        json={
            "mode": "shadow",
            "recommendation": {
                "recommendation_id": "rec",
                "source_state_id": "cfs",
                "field_id": "field",
                "status": "approved",
                "decision": {"operator_approved": True},
            },
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "safety_blocked"


def test_phase9_model_register_api_promotes_champion():
    c = _client()
    res = c.post(
        "/v1/phase9/autonomy/models/register",
        json={
            "name": "water-demand",
            "task": "irrigation",
            "version": "1.0.0",
            "metrics": {"r2": 0.9},
            "training_feature_sets": ["canonical_field_runtime_v1"],
            "promote_thresholds": {"r2": 0.8},
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "champion"
