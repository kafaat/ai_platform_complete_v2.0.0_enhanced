import os

from api.phase10_continuous_learning import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

# phase9-12 routers مؤمَّنة بتوكن خدمة على مستوى الراوتر؛ نضبط السرّ ونمرّر الترويسة.
os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-agent-token")


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, headers={"X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"]})


def _records():
    return [
        {
            "feature_id": f"feat_{i}",
            "entity_type": "field",
            "entity_id": f"field-{i % 2}",
            # Explicit temporal lineage: without it a dataset is not trainable.
            "tenant_id": "tenant-one",
            "source_version": "fixture-source-v1",
            "event_time": f"2026-06-26T{i:02d}:00:00+00:00",
            "available_at": f"2026-06-26T{i:02d}:01:00+00:00",
            "ingested_at": f"2026-06-26T{i:02d}:02:00+00:00",
            "prediction_at": f"2026-06-26T{i:02d}:03:00+00:00",
            "features": {"ndvi": 0.5, "etc_mm": 5 + i},
            "labels": {"net_benefit": 10 + i},
        }
        for i in range(12)
    ]


def test_phase10_dataset_api_trainable():
    res = _client().post("/v1/phase10/learning/dataset", json={"records": _records()})
    assert res.status_code == 200
    assert res.json()["status"] == "trainable"


def test_phase10_dataset_api_blocks_rows_without_temporal_lineage():
    # Negative control: the same rows without availability/ingestion/prediction times.
    legacy = [
        {k: v for k, v in r.items() if k not in {"available_at", "ingested_at", "prediction_at"}}
        for r in _records()
    ]
    res = _client().post("/v1/phase10/learning/dataset", json={"records": legacy})
    assert res.status_code == 200
    assert res.json()["status"] == "blocked"
    assert "temporal_integrity_unverified" in res.json()["quality"]["blocked_reasons"]


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
