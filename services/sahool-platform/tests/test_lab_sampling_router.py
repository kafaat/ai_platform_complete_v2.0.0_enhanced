from api.routers.soil_sampling import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_lab_sampling_api_roundtrip_and_context():
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    sample = c.post(
        "/api/v1/lab/samples",
        json={
            "field_id": "field-a",
            "kind": "soil",
            "latitude": 15.12,
            "longitude": 44.22,
            "depth_cm_from": 0,
            "depth_cm_to": 30,
            "status": "collected",
        },
    )
    assert sample.status_code == 200
    sid = sample.json()["sample_id"]
    soil = c.post(
        "/api/v1/lab/soil-results",
        json={
            "sample_id": sid,
            "ph": 7.2,
            "ec_dsm": 1.1,
            "organic_matter_pct": 2.2,
            "nitrogen_mg_kg": 30,
            "phosphorus_mg_kg": 18,
            "potassium_mg_kg": 220,
            "approved": True,
        },
    )
    assert soil.status_code == 200
    assert soil.json()["decision_usable"] is True
    rows = c.get("/api/v1/lab/samples", params={"field_id": "field-a"}).json()
    assert rows and rows[0]["ph"] == 7.2
    ctx = c.get("/api/v1/fields/field-a/lab-context").json()
    assert ctx["soil_lab_ready_for_fertilizer"] is True
    assert ctx["recommendation_gate"] == "allow"
