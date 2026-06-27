from api.phase10_continuous_learning import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _records():
    return [
        {
            "feature_id": f"feat_{i}",
            "entity_type": "field",
            "entity_id": f"field-{i % 2}",
            "features": {"ndvi": 0.5, "etc_mm": 5 + i},
            "labels": {"net_benefit": 10 + i},
        }
        for i in range(12)
    ]


def test_phase10_dataset_api_trainable():
    res = _client().post("/v1/phase10/learning/dataset", json={"records": _records()})
    assert res.status_code == 200
    assert res.json()["status"] == "trainable"


def test_phase10_scenario_api_returns_projection():
    res = _client().post(
        "/v1/phase10/learning/scenario",
        json={
            "field_state": {
                "field_id": "f1",
                "state": {"state_id": "s1", "operational_truths": {"yield_t_ha": 4}},
            },
            "scenario": {"rainfall_delta_pct": -20, "baseline_yield_t_ha": 4},
        },
    )
    assert res.status_code == 200
    assert res.json()["field_id"] == "f1"
    assert "yield_t_ha" in res.json()["projected"]
