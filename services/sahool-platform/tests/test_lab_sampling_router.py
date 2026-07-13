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
    quality = {}  # sample_id -> quality_status (unreviewed|approved), منفصل عن قاموس التحاليل

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
        # الإدخال العاديّ يُنشئ نتيجة غير مُعتمَدة (approved=False دائماً بعد التحصين).
        # قاموس التحاليل نظيف (مفاتيح analyte + sample_id + approved) كي يقبله SoilLabResult؛
        # حالة الجودة تُتبَّع منفصلةً في quality.
        results[sample_id] = {a["analyte"]: a["value"] for a in analytes}
        results[sample_id].update(sample_id=sample_id, approved=approved)
        quality[sample_id] = "unreviewed"
        return analytes

    async def has_soil_result(conn, *, tenant_id, sample_id):
        return sample_id in results

    async def approve_soil_results(conn, *, tenant_id, sample_id, approved_by):
        if sample_id in results:
            quality[sample_id] = "approved"
            results[sample_id]["approved"] = True
            return 1
        return 0

    async def list_samples(conn, *, tenant_id, field_id=None):
        rows = list(samples.values())
        return [r for r in rows if field_id is None or r["field_id"] == field_id]

    async def latest_soil_analysis(conn, *, tenant_id, field_id):
        # يُطابِق العقد الحقيقيّ: يُرجِع فقط نتيجة مُعتمَدة (quality='approved') لعيّنة
        # بحالة approved/published، بقاموس تحاليل نظيف ومعلَّم approved=True.
        for sid, row in samples.items():
            if (
                row["field_id"] == field_id
                and sid in results
                and quality.get(sid) == "approved"
                and row["status"] in {"approved", "published"}
            ):
                return {**results[sid], "approved": True}
        return None

    async def latest_water_analysis(*args, **kwargs):
        return None

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod.lab_store, "create_sample", create_sample)
    monkeypatch.setattr(mod.lab_store, "add_custody_event", add_custody_event)
    monkeypatch.setattr(mod.lab_store, "get_sample", get_sample)
    monkeypatch.setattr(mod.lab_store, "set_status", set_status)
    monkeypatch.setattr(mod.lab_store, "insert_soil_results", insert_soil_results)
    monkeypatch.setattr(mod.lab_store, "has_soil_result", has_soil_result)
    monkeypatch.setattr(mod.lab_store, "approve_soil_results", approve_soil_results)
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
        # الإدخال العاديّ لا يقبل approved (حُذِف من العقد): يُنشئ نتيجة غير مُعتمَدة
        # بحالة result_received، وغير قابلة للقرار حتى الاعتماد.
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
                "observed_at": datetime.now(UTC).isoformat(),
            },
        )
        assert soil.status_code == 200
        assert soil.json()["decision_usable"] is False
        rows = c.get("/api/v1/lab/samples", params={"field_id": "field-a"}).json()
        assert rows and rows[0]["status"] == "result_received"
        ctx = c.get("/api/v1/fields/field-a/lab-context").json()
        assert ctx["soil_lab_ready_for_fertilizer"] is False

        # الاعتماد عبر انتقال الحالة المُصرَّح به فقط (فصل الواجبات) — يَختِم النتيجة
        # بهويّة المُعتمِد فتُصبح قابلة للقرار.
        transition = c.post(
            f"/api/v1/lab/samples/{sid}/transition",
            json={"target_status": "approved"},
        )
        assert transition.status_code == 200
        rows = c.get("/api/v1/lab/samples", params={"field_id": "field-a"}).json()
        assert rows[0]["status"] == "approved"
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
                "supersedes_result_ids": {"ec_dsm": "00000000-0000-0000-0000-000000000123"},
                "correction_reason": "instrument recalibration",
            },
        )
        assert response.status_code == 200
        # تصحيح عيّنة منشورة يُقبَل ويُعيدها لـresult_received (نتيجة غير مُعتمَدة بانتظار
        # إعادة اعتماد مُصرَّح به ثمّ إعادة نشر) — لا اعتماد ذاتيّ من مُدخِل التصحيح.
        assert captured["status"] == "result_received"
        assert captured["correction_reason"] == "instrument recalibration"
    finally:
        app.dependency_overrides.clear()
