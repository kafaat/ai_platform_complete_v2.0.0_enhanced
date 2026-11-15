from contextlib import asynccontextmanager
from datetime import UTC, datetime, timezone

from api.main import get_current_user
from api.routers import soil_sampling as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _user(user_id="u1", role=UserRole.MANAGER):
    return UserSchema(
        user_id=user_id,
        tenant_id="00000000-0000-0000-0000-000000000001",
        role=role,
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

    authors = set()

    async def current_authors(*args):
        return authors

    monkeypatch.setattr(mod.lab_store, "result_entry_actors", current_authors)

    async def add_custody_event(*args, **kwargs):
        if kwargs["event_type"] == "lab_result_received":
            authors.add(kwargs["actor_id"])
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
        for item in analytes:
            if item["analyte"] == "ec_dsm":
                results[sample_id]["ec_extraction_method"] = item["method_code"]
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

    async def list_samples(conn, *, tenant_id, field_id=None, sample_id=None):
        rows = list(samples.values())
        return [r for r in rows if field_id is None or r["field_id"] == field_id]

    async def latest_soil_analysis(conn, *, tenant_id, field_id, sample_id=None):
        # يُطابِق العقد الحقيقيّ: يُرجِع فقط نتيجة مُعتمَدة (quality='approved') لعيّنة
        # بحالة approved/published، بقاموس تحاليل نظيف ومعلَّم approved=True.
        for sid, row in samples.items():
            if (
                row["field_id"] == field_id
                and (sample_id is None or sid == sample_id)
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
    app.dependency_overrides[get_current_user] = lambda: _user()
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
                "ec_extraction_method": "saturated_paste",
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
        assert (
            c.post(
                f"/api/v1/lab/samples/{sid}/transition", json={"target_status": "approved"}
            ).status_code
            == 403
        )
        app.dependency_overrides[get_current_user] = lambda: _user("reviewer", UserRole.AGRONOMIST)
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
    app.dependency_overrides[get_current_user] = lambda: _user()
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


def _idempotency_harness(monkeypatch):
    """Lab-sample router with a fake sample store and an in-memory command store."""
    created = []
    commands = {}

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield object()

    async def create_sample(conn, *, tenant_id, created_by, payload):
        row = dict(payload)
        row.update(
            sample_id=f"s-{len(created) + 1}",
            tenant_id=tenant_id,
            created_by=created_by,
            created_at=datetime(2026, 10, 26, tzinfo=UTC),
        )
        created.append(row)
        return row

    async def add_custody_event(*args, **kwargs):
        return {"event_id": "e1"}

    class FakeCommandStore:
        def __init__(self, pool, conn=None):
            pass

        async def insert(self, cmd):
            if cmd.command_id in commands:
                return False
            commands[cmd.command_id] = cmd
            return True

        async def get(self, command_id):
            return commands.get(command_id)

        async def mark_succeeded(self, command_id, result):
            from api.command_store import CommandStatus

            commands[command_id].status = CommandStatus.SUCCEEDED
            commands[command_id].result = result

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    # raising=False: على كودٍ لا يستورد الاسمين يُقاس السلوك (تنفيذٌ مكرَّر) لا خطأ التجهيز.
    monkeypatch.setattr(mod, "CommandStore", FakeCommandStore, raising=False)
    monkeypatch.setattr(mod, "get_pool", lambda: None, raising=False)
    monkeypatch.setattr(mod.lab_store, "create_sample", create_sample)
    monkeypatch.setattr(mod.lab_store, "add_custody_event", add_custody_event)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app), created


_SAMPLE = {
    "field_id": "field-a",
    "kind": "soil",
    "latitude": 15.12,
    "longitude": 44.22,
    "depth_cm_from": 0,
    "depth_cm_to": 30,
    "status": "collected",
}
_REPLAY_ID = "6f1c2a6e-3c4b-4d9e-9a51-2a7b0c1d2e3f"


def test_replayed_sample_with_the_same_key_creates_one_sample(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    first = c.post("/api/v1/lab/samples", json=_SAMPLE, headers={"Idempotency-Key": _REPLAY_ID})
    again = c.post("/api/v1/lab/samples", json=_SAMPLE, headers={"Idempotency-Key": _REPLAY_ID})
    assert first.status_code == 200 and again.status_code == 200
    assert len(created) == 1
    assert again.json()["sample_id"] == first.json()["sample_id"] == "s-1"


def test_same_key_with_a_different_sample_is_rejected(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    c.post("/api/v1/lab/samples", json=_SAMPLE, headers={"Idempotency-Key": _REPLAY_ID})
    other = dict(_SAMPLE, latitude=15.5)
    resp = c.post("/api/v1/lab/samples", json=other, headers={"Idempotency-Key": _REPLAY_ID})
    assert resp.status_code == 409
    assert len(created) == 1


def test_without_a_key_each_post_creates_a_sample(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    c.post("/api/v1/lab/samples", json=_SAMPLE)
    c.post("/api/v1/lab/samples", json=_SAMPLE)
    assert len(created) == 2


def test_a_malformed_key_is_rejected(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    resp = c.post("/api/v1/lab/samples", json=_SAMPLE, headers={"Idempotency-Key": "not-a-uuid"})
    assert resp.status_code == 400
    assert created == []


def test_texture_labels_normalise_and_unknown_labels_are_rejected():
    import pytest
    from pydantic import ValidationError

    def result(**kw):
        return mod.SoilLabResultIn(sample_id="s", **kw)

    assert result(texture="Sandy_Loam").texture == "sandy loam"
    assert result(texture="طمية").texture == "loam"  # no shadda
    assert result(texture="طميّة", sand_pct=40, silt_pct=40, clay_pct=20).texture == "loam"
    assert result(sand_pct=40, silt_pct=39.5, clay_pct=20.5).texture == "loam"  # 100 ± 1
    for bad in (
        {"texture": "loamy-ish"},
        {"sand_pct": 40, "silt_pct": 40},
        {"sand_pct": 40, "silt_pct": 38.9, "clay_pct": 20},
        {"sand_pct": 40, "silt_pct": 40, "clay_pct": 20, "texture": "clay"},
    ):
        with pytest.raises(ValidationError):
            result(**bad)


def test_blank_plan_id_from_older_clients_means_no_plan():
    sample = mod.LabSampleIn(
        field_id="f",
        kind="soil",
        latitude=15,
        longitude=44,
        depth_cm_from=0,
        depth_cm_to=30,
        sampling_plan_id="",
    )
    assert sample.sampling_plan_id is None


def test_fraction_correction_supersedes_the_whole_texture_group(monkeypatch):
    captured = {}

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield object()

    async def get_sample(*args, **kwargs):
        return {"sample_id": "s-1", "field_id": "f-1", "kind": "soil", "status": "published"}

    async def current_soil_result_ids(conn, *, tenant_id, sample_id, analytes):
        captured["asked"] = sorted(analytes)
        return {a: f"old-{a}" for a in analytes}

    async def insert_soil_results(*args, **kwargs):
        captured["analytes"] = {a["analyte"]: a for a in kwargs["analytes"]}
        return []

    async def noop(*args, **kwargs):
        return {"sample_id": "s-1", "status": kwargs.get("status")}

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod.lab_store, "get_sample", get_sample)
    monkeypatch.setattr(mod.lab_store, "current_soil_result_ids", current_soil_result_ids)
    monkeypatch.setattr(mod.lab_store, "insert_soil_results", insert_soil_results)
    monkeypatch.setattr(mod.lab_store, "set_status", noop)
    monkeypatch.setattr(mod.lab_store, "add_custody_event", noop)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    explicit = "00000000-0000-0000-0000-000000000123"
    response = TestClient(app).post(
        "/api/v1/lab/soil-results",
        json={
            "sample_id": "s-1",
            "clay_pct": 30,
            "sand_pct": 40,
            "silt_pct": 30,
            "supersedes_result_ids": {"clay_pct": explicit},
            "correction_reason": "clay re-run",
        },
    )
    assert response.status_code == 200, response.text
    sent = captured["analytes"]
    assert str(sent["clay_pct"]["supersedes_result_id"]) == explicit
    assert captured["asked"] == ["sand_pct", "silt_pct", "texture"]
    assert sent["texture"]["value"] == "clay loam"
    assert sent["texture"]["supersedes_result_id"] == "old-texture"
    assert sent["sand_pct"]["supersedes_result_id"] == "old-sand_pct"


def test_soil_ec_method_separates_reference_and_dilution():
    import pytest
    from pydantic import ValidationError

    for method in ("saturated_paste", "soil_water_1_1", "soil_water_1_2_5", "soil_water_1_5", None):
        payload = mod.SoilLabResultIn(
            sample_id="sample",
            ec_dsm=8.4,
            ph=7.2,
            method_code="lab-SOP",
            ec_extraction_method=method,
        )
        rows = {row["analyte"]: row for row in mod._analytes(payload)}
        assert rows["ec_dsm"]["method_code"] == (method or "lab-SOP")
        assert rows["ph"]["method_code"] == "lab-SOP"
        result = mod._interpret_lab_values({"sample_id": "sample", "ec_dsm": 8.4}, method)
        salinity = result["classification"]["salinity_ec"]
        assert (salinity["class"] is not None) == (method == "saturated_paste")
        assert salinity["value_dsm"] == 8.4
    with pytest.raises(ValidationError):
        mod.SoilLabResultIn(sample_id="sample", ph=7.2, ec_extraction_method="saturated_paste")


def _capture_soil_publication(monkeypatch):
    import asyncio

    from api import soil_evidence_bridge as bridge

    sent = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            n = len(sent["json"]["properties"])
            return {"status": "accepted", "observation_ids": [f"sob_{i}" for i in range(n)]}

    class _Client:
        def __init__(self, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, json, headers):
            sent["json"] = json
            return _Response()

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-only")
    monkeypatch.setattr(bridge.httpx, "AsyncClient", _Client)
    return sent, bridge, asyncio


def test_published_value_comes_from_the_row_whose_id_is_recorded(monkeypatch):
    sent, bridge, asyncio = _capture_soil_publication(monkeypatch)
    observed = datetime(2026, 11, 1, 8, tzinfo=UTC)
    rows = [  # publishable order: the first row per analyte is the one recorded
        # saturated paste: the method that publishes as soil "ec"
        {
            "analyte": "ec_dsm",
            "result_id": "r-new",
            "value_json": "1.7",
            "observed_at": observed,
            "method_code": "saturated_paste",
        },
        {
            "analyte": "ec_dsm",
            "result_id": "r-old",
            "value_json": "1.2",
            "observed_at": observed,
            "method_code": "saturated_paste",
        },
        {"analyte": "ph", "result_id": "r-ph", "value_json": "7.1", "observed_at": observed},
    ]
    receipt = asyncio.run(
        bridge.publish_soil_lab_evidence(
            tenant_id="00000000-0000-0000-0000-000000000001",
            field_id="pivot",
            sample={"sample_id": "s-1"},
            results={"ec_dsm": 1.2, "ph": 7.1},  # a value from a different row than r-new
            result_rows=rows,
        )
    )
    assert sent["json"]["properties"] == {"ph": 7.1, "ec": 1.7}
    assert receipt["result_by_canonical"]["ec"] == "r-new"
    # soil-service's canonical units win; the lab's labels stay in provenance only.
    assert "units" not in sent["json"]
    assert sent["json"]["provenance"]["observed_at_source"] == "laboratory_result"


# ── Gap P6: a plan-point sample stores the origin soil-service resolves, never the claim ─────
import importlib.util  # noqa: E402
import json as _json  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
from api import soil_hydraulic_client  # noqa: E402

_SOIL_ORIGIN_PATH = Path(__file__).resolve().parents[2] / "soil-service" / "plan_origin.py"
_spec = importlib.util.spec_from_file_location("soil_service_plan_origin", _SOIL_ORIGIN_PATH)
_soil_origin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_soil_origin)

_PLAN_POINT = {
    "sample_id": "ss-1",
    "zone_id": "Z1",
    "point": {"type": "Point", "coordinates": [44.0, 16.0]},
    "depth_cm": [0, 30],
    "indicators": ["ndvi"],
    "indicator_sources": {"ndvi": {"scene_id": "S2A_20260501", "acquisition_date": "2026-05-01"}},
}
#: The client's claim: the plan point it says it sampled, with an invented scene. The actual
#: collection position (``latitude``/``longitude``) is about 66 km north of the planned point.
_PLAN_SAMPLE = {
    **_SAMPLE,
    "latitude": 16.6,
    "longitude": 44.0,
    "sampling_plan_id": "ssp-1",
    "sampling_origin": {
        "point_id": "ss-1",
        "zone_id": "Z1",
        "latitude": 16.6,
        "longitude": 44.0,
        "indicators": ["ndvi"],
        "indicator_sources": {"ndvi": {"scene_id": "INVENTED", "acquisition_date": "2026-01-01"}},
    },
}


def _soil_service(monkeypatch, *, plans=None, fail=None):
    """soil-service's origin route, answered by its own resolver over its stored copies."""
    stored = {"ssp-1": [_PLAN_POINT]} if plans is None else plans
    calls = []

    async def soil_post(path, *, tenant_id, body):
        calls.append(path)
        if fail is not None:
            raise soil_hydraulic_client.SamplingPlanVerificationUnavailable(fail)
        plan_id = path.split("/")[-2]
        if plan_id not in stored:
            detail = {"code": "sampling_plan_not_found", "plan_id": plan_id}
            return httpx.Response(404, json={"detail": detail})
        try:
            origin = _soil_origin.resolve_origin(
                plan_id=plan_id,
                plan_digest_value="f" * 64,
                sample_points=stored[plan_id],
                point_id=body["point_id"],
                latitude=body["latitude"],
                longitude=body["longitude"],
                gps_accuracy_m=body["gps_accuracy_m"],
                deviation_reason=body["deviation_reason"],
                claimed=body["claimed"],
            )
        except _soil_origin.OriginRefused as exc:
            return httpx.Response(exc.status, json={"detail": exc.detail()})
        return httpx.Response(200, content=_json.dumps(origin))

    monkeypatch.setattr(soil_hydraulic_client, "_soil_post", soil_post)
    return calls


def test_p6_negative_control_a_66_km_origin_is_refused_and_nothing_is_stored(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    _soil_service(monkeypatch)
    resp = c.post("/api/v1/lab/samples", json=_PLAN_SAMPLE)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "sampling_origin_out_of_tolerance"
    assert 66_000 < detail["deviation_m"] < 67_000
    assert created == []


def test_p6_a_stated_reason_stores_the_server_resolved_origin_not_the_claim(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    _soil_service(monkeypatch)
    body = {**_PLAN_SAMPLE, "deviation_reason": "planned point flooded, sampled upslope"}
    resp = c.post("/api/v1/lab/samples", json=body)
    assert resp.status_code == 200, resp.text
    origin = created[0]["sampling_origin"]
    assert (origin["latitude"], origin["longitude"]) == (16.0, 44.0)  # the stored plan point
    assert origin["indicator_sources"]["ndvi"]["scene_id"] == "S2A_20260501"
    assert origin["verification"] == "stored_plan" and origin["resolved_by"] == "soil-service"
    assert "indicator_sources" in origin["client_claim_mismatch"]
    collection = origin["collection"]
    assert collection["on_plan"] is False
    assert collection["deviation_reason"] == "planned point flooded, sampled upslope"
    assert (collection["latitude"], collection["longitude"]) == (16.6, 44.0)


def test_p6_an_in_tolerance_plan_sample_is_stored_on_plan(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    _soil_service(monkeypatch)
    resp = c.post("/api/v1/lab/samples", json={**_PLAN_SAMPLE, "latitude": 16.0001})
    assert resp.status_code == 200, resp.text
    assert created[0]["sampling_origin"]["collection"]["on_plan"] is True


def test_p6_a_plan_never_stored_is_refused(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    calls = _soil_service(monkeypatch, plans={})
    resp = c.post("/api/v1/lab/samples", json={**_PLAN_SAMPLE, "latitude": 16.0})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "sampling_plan_not_found"
    assert calls and created == []


def test_p6_soil_service_unreachable_fails_closed_for_plan_samples_only(monkeypatch):
    c, created = _idempotency_harness(monkeypatch)
    _soil_service(monkeypatch, fail="ConnectError")
    resp = c.post("/api/v1/lab/samples", json={**_PLAN_SAMPLE, "latitude": 16.0})
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "sampling_plan_verification_unavailable"
    assert created == []
    manual = c.post("/api/v1/lab/samples", json=_SAMPLE)
    assert manual.status_code == 200
    assert created[0]["sampling_origin"] is None


def test_p6_a_plan_id_without_a_plan_point_is_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        mod.LabSampleIn(**{**_SAMPLE, "sampling_plan_id": "ssp-1"})
    with pytest.raises(ValidationError):
        mod.LabSampleIn(**{**_SAMPLE, "deviation_reason": "no plan to deviate from"})
