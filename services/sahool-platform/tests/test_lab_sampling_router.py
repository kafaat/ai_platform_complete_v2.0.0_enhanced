from contextlib import asynccontextmanager
from datetime import UTC, datetime, timezone

from api.main import get_current_user
from api.routers import soil_sampling as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _user():
    return UserSchema(
        user_id="u1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        role=UserRole.MANAGER,
        name_ar="مدير",
    )


def test_lab_sampling_api_roundtrip_and_context(monkeypatch):
    samples = {}
    results = {}

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield object()

    async def create_sample(conn, *, tenant_id, created_by, payload):
        row = dict(payload)
        row.update(sample_id="s-123", tenant_id=tenant_id, created_by=created_by)
        samples[row["sample_id"]] = row
        return row

    async def add_custody_event(*args, **kwargs):
        return {"event_id": "e1"}

    async def get_sample(conn, *, tenant_id, sample_id):
        return samples.get(sample_id)

    async def set_status(conn, *, tenant_id, sample_id, status):
        samples[sample_id]["status"] = status
        return dict(samples[sample_id])

    async def insert_soil_results(
        conn,
        *,
        tenant_id,
        sample_id,
        analytes,
        observed_at,
        approved,
        approved_by,
        correction_reason=None,
    ):
        results[sample_id] = {a["analyte"]: a["value"] for a in analytes}
        results[sample_id].update(sample_id=sample_id, approved=approved)
        return analytes

    async def list_samples(conn, *, tenant_id, field_id=None):
        rows = list(samples.values())
        return [r for r in rows if field_id is None or r["field_id"] == field_id]

    async def latest_soil_analysis(conn, *, tenant_id, field_id):
        for sid, row in samples.items():
            if (
                row["field_id"] == field_id
                and sid in results
                and row["status"] in {"approved", "published"}
            ):
                return results[sid]
        return None

    async def latest_water_analysis(*args, **kwargs):
        return None

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod.lab_store, "create_sample", create_sample)
    monkeypatch.setattr(mod.lab_store, "add_custody_event", add_custody_event)
    monkeypatch.setattr(mod.lab_store, "get_sample", get_sample)
    monkeypatch.setattr(mod.lab_store, "set_status", set_status)
    monkeypatch.setattr(mod.lab_store, "insert_soil_results", insert_soil_results)
    monkeypatch.setattr(mod.lab_store, "list_samples", list_samples)
    monkeypatch.setattr(mod.lab_store, "latest_soil_analysis", latest_soil_analysis)
    monkeypatch.setattr(mod.lab_store, "latest_water_analysis", latest_water_analysis)

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    c = TestClient(app)
    try:
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
                "observed_at": datetime.now(UTC).isoformat(),
            },
        )
        assert soil.status_code == 200
        assert soil.json()["decision_usable"] is True
        rows = c.get("/api/v1/lab/samples", params={"field_id": "field-a"}).json()
        assert rows and rows[0]["status"] == "approved"
        ctx = c.get("/api/v1/fields/field-a/lab-context").json()
        assert ctx["soil_lab_ready_for_fertilizer"] is True
        assert ctx["recommendation_gate"] == "allow"
    finally:
        app.dependency_overrides.clear()


def test_published_sample_correction_is_accepted_for_republication(monkeypatch):
    from contextlib import asynccontextmanager

    captured = {}

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield object()

    async def get_sample(*args, **kwargs):
        return {"sample_id": "s-1", "field_id": "f-1", "kind": "soil", "status": "published"}

    async def insert_soil_results(*args, **kwargs):
        captured["correction_reason"] = kwargs.get("correction_reason")
        return []

    async def set_status(*args, **kwargs):
        captured["status"] = kwargs["status"]
        return {"sample_id": "s-1", "status": kwargs["status"]}

    async def add_custody_event(*args, **kwargs):
        return {}

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod.lab_store, "get_sample", get_sample)
    monkeypatch.setattr(mod.lab_store, "insert_soil_results", insert_soil_results)
    monkeypatch.setattr(mod.lab_store, "set_status", set_status)
    monkeypatch.setattr(mod.lab_store, "add_custody_event", add_custody_event)

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    c = TestClient(app)
    try:
        response = c.post(
            "/api/v1/lab/soil-results",
            json={
                "sample_id": "s-1",
                "ec_dsm": 3.4,
                "approved": True,
                "supersedes_result_ids": {"ec_dsm": "00000000-0000-0000-0000-000000000123"},
                "correction_reason": "instrument recalibration",
            },
        )
        assert response.status_code == 200
        assert captured["status"] == "approved"
        assert captured["correction_reason"] == "instrument recalibration"
    finally:
        app.dependency_overrides.clear()
