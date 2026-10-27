"""P3-AUTH: مهمّة raster مربوطة بمستأجِرها — توكن الخدمة وحده لا يكفي لقراءتها.

العطل: ``GET /v1/jobs/{id}`` و``/v1/jobs/{id}/result`` كانا يطلبان توكن الخدمة المشترك فقط،
و``/v1/process`` و``/v1/process/batch`` و``process-cdse`` لا يخزّنون مالكاً على المهمّة.
فمهمّةٌ أُنشئت للمستأجِر A تُقرأ بـ``X-Tenant-Id: B`` وتوكن صالح — والنتيجة تحمل
إحصاءات وحدوداً جغرافيّة ومعرّف طبقة وقالب بلاطات.

العقد بعد الإصلاح:
  * كلّ مسار إنشاء يربط المهمّة بمستأجِر الطلب (سياق البوّابة الموثوق، وإلّا جسم الطلب)؛
    والمهامّ الفرعيّة (دفعة/CDSE) ترث مالك المهمّة الأمّ.
  * القراءة لمهمّة ذات مالك تتطلّب مستأجِراً مطابقاً؛ المخالف أو الغائب ⇒ 404 مطابق
    لـ«مهمّة غير موجودة» (لا يُكشَف وجود معرّف مستأجِر آخر).
  * مهمّة بلا مالك (طلب بلا أيّ سياق مستأجِر، أو مهمّة قديمة في Redis قبل النشر) تبقى
    محكومة بتوكن الخدمة وحده — السلوك السابق، لا انحدار على مستدعٍ لا يملك مستأجِراً.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
import raster_api_models as api_models
import raster_job_orchestration
import raster_settings
from fastapi.testclient import TestClient
from job_store import JobStore
from raster_runtime_state import JOBS

TOKEN = "job-tenant-test-token"
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture()
def client(monkeypatch):
    import main

    # مصدران للتوكن: raster_settings (routers/jobs، processing) و``main.AGENT_TOKEN``
    # (raster_field_runtime — مسار process-cdse)؛ قد يضبط اختبارٌ سابق أحدهما.
    monkeypatch.setattr(raster_settings, "AGENT_TOKEN", TOKEN)
    monkeypatch.setattr(main, "AGENT_TOKEN", TOKEN, raising=False)
    return TestClient(main.app)


def _headers(tenant: str | None) -> dict[str, str]:
    headers = {"X-Agent-Token": TOKEN}
    if tenant is not None:
        headers["X-Tenant-Id"] = tenant
    return headers


def _seed_completed_job(job_id: str, tenant: str | None) -> None:
    job = {
        "job_id": job_id,
        "status": api_models.JobStatus.completed,
        "progress_pct": 100,
        "created_at": "2026-10-27T00:00:00+00:00",
        "result": {"layer_id": f"layer-of-{tenant}", "stats": {"mean": 0.5}},
    }
    if tenant is not None:
        job["tenant_id"] = tenant
    JOBS.set(job_id, job)


@pytest.mark.parametrize("suffix", ["", "/result"])
def test_owned_job_is_hidden_from_foreign_tenant(client, suffix):
    _seed_completed_job("job_owned_by_a", TENANT_A)
    foreign = client.get(f"/v1/jobs/job_owned_by_a{suffix}", headers=_headers(TENANT_B))
    assert foreign.status_code == 404, foreign.text
    missing = client.get(f"/v1/jobs/job_does_not_exist{suffix}", headers=_headers(TENANT_B))
    # نفس الردّ تماماً كمهمّة غير موجودة: لا تعداد لمعرّفات مستأجِر آخر.
    assert foreign.json() == missing.json()


@pytest.mark.parametrize("suffix", ["", "/result"])
def test_owned_job_requires_a_tenant_context(client, suffix):
    _seed_completed_job("job_owned_by_a_ctx", TENANT_A)
    resp = client.get(f"/v1/jobs/job_owned_by_a_ctx{suffix}", headers=_headers(None))
    assert resp.status_code == 404, resp.text


def test_owned_job_is_readable_by_its_tenant(client):
    _seed_completed_job("job_owned_by_a_ok", TENANT_A)
    status = client.get("/v1/jobs/job_owned_by_a_ok", headers=_headers(TENANT_A))
    assert status.status_code == 200 and status.json()["status"] == "completed"
    result = client.get("/v1/jobs/job_owned_by_a_ok/result", headers=_headers(TENANT_A))
    assert result.status_code == 200 and result.json()["layer_id"] == f"layer-of-{TENANT_A}"


def test_service_token_is_still_required(client):
    _seed_completed_job("job_owned_by_a_tok", TENANT_A)
    resp = client.get("/v1/jobs/job_owned_by_a_tok", headers={"X-Tenant-Id": TENANT_A})
    assert resp.status_code == 401


def test_unowned_job_keeps_service_token_contract(client):
    _seed_completed_job("job_without_owner", None)
    assert client.get("/v1/jobs/job_without_owner", headers=_headers(None)).status_code == 200
    assert client.get("/v1/jobs/job_without_owner", headers=_headers(TENANT_B)).status_code == 200


_BANDS = {"red": 1, "nir": 2}


def test_process_binds_job_to_request_tenant(client, monkeypatch):
    import raster_processing_runtime

    monkeypatch.setattr(raster_processing_runtime, "run_processing", lambda *a, **k: None)
    resp = client.post(
        "/v1/process",
        json={
            "tenant_id": TENANT_A,
            "raster_url": "https://example.invalid/scene.tif",
            "indicator": "ndvi",
            "source_format": "sentinel2_l2a",
            "bands": _BANDS,
        },
        headers=_headers(TENANT_A),
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    assert JOBS.get(job_id)["tenant_id"] == TENANT_A
    assert client.get(f"/v1/jobs/{job_id}", headers=_headers(TENANT_B)).status_code == 404
    assert client.get(f"/v1/jobs/{job_id}", headers=_headers(TENANT_A)).status_code == 200


def test_process_without_header_binds_body_tenant(client, monkeypatch):
    import raster_processing_runtime

    monkeypatch.setattr(raster_processing_runtime, "run_processing", lambda *a, **k: None)
    resp = client.post(
        "/v1/process",
        json={
            "tenant_id": TENANT_A,
            "raster_url": "https://example.invalid/scene.tif",
            "indicator": "ndvi",
            "source_format": "sentinel2_l2a",
            "bands": _BANDS,
        },
        headers=_headers(None),
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    assert JOBS.get(job_id)["tenant_id"] == TENANT_A
    assert client.get(f"/v1/jobs/{job_id}", headers=_headers(TENANT_B)).status_code == 404


def test_batch_binds_job_to_request_tenant(client, monkeypatch):
    import raster_batch_job_store
    import raster_processing_runtime

    async def _unavailable(**kwargs):
        return raster_batch_job_store.DurableClaim(False, False, kwargs["job_id"], "unavailable")

    monkeypatch.setattr(raster_batch_job_store, "claim_or_recover", _unavailable)
    monkeypatch.setattr(raster_processing_runtime, "run_batch_processing", lambda *a, **k: None)
    resp = client.post(
        "/v1/process/batch",
        json={
            "tenant_id": TENANT_A,
            "field_id": "field-job-tenant-batch",
            "raster_url": "https://example.invalid/scene-batch-tenant.tif",
            "indicators": ["ndvi", "ndmi"],
            "source_format": "sentinel2_l2a",
            "bands": _BANDS,
        },
        headers=_headers(TENANT_A),
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    assert JOBS.get(job_id)["tenant_id"] == TENANT_A
    assert client.get(f"/v1/jobs/{job_id}", headers=_headers(TENANT_B)).status_code == 404


def test_cdse_binds_job_to_request_tenant(client, monkeypatch):
    import cdse_client
    import imagery_source_gate
    import routers.fields as fields_router

    monkeypatch.setattr(cdse_client, "is_configured", lambda: True)
    monkeypatch.setattr(imagery_source_gate, "enforce_enabled", lambda: False)
    monkeypatch.setattr(fields_router, "_run_cdse_processing", lambda *a, **k: None)
    resp = client.post(
        "/v1/fields/field-job-tenant-cdse/process-cdse",
        json={"bbox": [44.0, 15.0, 44.01, 15.01], "indicators": ["ndvi"]},
        headers=_headers(TENANT_A),
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    assert JOBS.get(job_id)["tenant_id"] == TENANT_A
    assert client.get(f"/v1/jobs/{job_id}", headers=_headers(TENANT_B)).status_code == 404


def test_batch_sub_jobs_inherit_parent_owner():
    """المهمّة الفرعيّة ``{job}_{ind}`` تُقرأ عبر ``/v1/jobs/{id}/result`` (imagery_automation)."""
    store = JobStore(None)
    seen: dict[str, dict] = {}

    def _record_sub_job(sub_job_id, _single):
        seen[sub_job_id] = dict(store.get(sub_job_id) or {})

    ctx = SimpleNamespace(
        _jobs=store,
        JobStatus=api_models.JobStatus,
        ProcessRequest=api_models.ProcessRequest,
        _run_processing=_record_sub_job,
        logger=logging.getLogger("test-job-tenant"),
    )
    store.set("batch_parent", {"job_id": "batch_parent", "tenant_id": TENANT_A})
    req = api_models.BatchProcessRequest(
        tenant_id=TENANT_A,
        raster_url=None,
        indicators=["ndvi", "ndmi"],
        source_format="sentinel2_l2a",
        bands=_BANDS,
    )
    raster_job_orchestration.run_batch_processing(ctx, "batch_parent", req)
    assert set(seen) == {"batch_parent_ndvi", "batch_parent_ndmi"}
    assert {sid: s.get("tenant_id") for sid, s in seen.items()} == {
        "batch_parent_ndvi": TENANT_A,
        "batch_parent_ndmi": TENANT_A,
    }


def test_cdse_sub_jobs_inherit_parent_owner(monkeypatch, tmp_path):
    """``run_cdse_processing`` كان يترك الفرعيّة تُنشأ ضمنيّاً بلا مالك داخل run_processing."""
    import cdse_client
    import raster_cdse_processing

    class _StubClient:
        def process_index(self, **_kwargs):
            return b"II*\x00stub-tiff"

    monkeypatch.setattr(cdse_client, "get_client", lambda: _StubClient())
    monkeypatch.setattr(cdse_client, "supported_indices", lambda: {"ndvi", "ndmi"})
    store = JobStore(None)
    seen: dict[str, dict] = {}

    def _record_sub_job(sub_job_id, _preq):
        seen[sub_job_id] = dict(store.get(sub_job_id) or {})

    ctx = SimpleNamespace(
        _jobs=store,
        JobStatus=api_models.JobStatus,
        ProcessRequest=api_models.ProcessRequest,
        IndicatorKind=api_models.IndicatorKind,
        SourceFormat=api_models.SourceFormat,
        BandMapping=api_models.BandMapping,
        UPLOAD_DIR=str(tmp_path),
        _run_processing=_record_sub_job,
        logger=logging.getLogger("test-job-tenant"),
    )
    store.set("cdse_parent", {"job_id": "cdse_parent", "tenant_id": TENANT_A})
    req = api_models.ProcessCdseRequest(
        bbox=[44.0, 15.0, 44.01, 15.01],
        indicators=["ndvi", "ndmi"],
        date_from="2026-10-01",
    )
    raster_cdse_processing.run_cdse_processing(ctx, "cdse_parent", "field-cdse-sub", req)
    assert {sid: s.get("tenant_id") for sid, s in seen.items()} == {
        "cdse_parent_ndvi": TENANT_A,
        "cdse_parent_ndmi": TENANT_A,
    }
