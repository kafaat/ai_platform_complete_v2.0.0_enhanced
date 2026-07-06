import os
import sys
import types

import main
from fastapi.testclient import TestClient


def _poly():
    return {
        "type": "Polygon",
        "coordinates": [[[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.01], [44.0, 15.0]]],
    }


def _scene(month: str, suffix: str, cloud: float):
    return {
        "item_id": f"S2_{month}_{suffix}",
        "datetime": f"{month}-15T08:00:00Z",
        "cloud_cover_pct": cloud,
        "bands_urls": {
            "blue": "https://example.com/blue.tif",
            "green": "https://example.com/green.tif",
            "red": "https://example.com/red.tif",
            "nir": "https://example.com/nir.tif",
            "scl": "https://example.com/scl.tif",
        },
    }


def test_backfill_policy_exposes_switchable_presets():
    client = TestClient(main.app)
    resp = client.get("/v1/imagery/backfill/policy")
    assert resp.status_code == 200
    data = resp.json()
    # الافتراضيّ الآن سنتان (نافذة المقارنة الموسميّة) بدل ١٢ شهراً.
    assert data["default_preset"] == "last_2_years"
    assert data["presets"]["last_2_years"]["months"] == 24
    assert data["presets"]["auto_12_months"]["months"] == 12
    assert data["presets"]["extended_3_years"]["months"] == 36
    assert data["presets"]["research_5_years"]["months"] == 60
    assert "custom" in data["presets"]


def test_backfill_dry_run_builds_jobs_from_custom_range(monkeypatch):
    monkeypatch.setattr(main, "AGENT_TOKEN", "test-token")
    calls = []

    async def fake_search(bbox, dt_start, dt_end, max_cloud, limit):
        calls.append((bbox, dt_start, dt_end, max_cloud, limit))
        month = dt_start[:7]
        return {"count": 2, "items": [_scene(month, "A", 18.0), _scene(month, "B", 6.0)]}

    monkeypatch.setattr(main, "_stac_search", fake_search)
    client = TestClient(main.app)
    resp = client.post(
        "/v1/fields/F-1/imagery/backfill",
        headers={"x-agent-token": "test-token", "x-tenant-id": "T-1"},
        json={
            "tenant_id": "T-1",
            "preset": "custom",
            "from_date": "2026-01-01",
            "to_date": "2026-02-28",
            "indices": ["ndvi", "ndmi"],
            "limit_per_month": 1,
            "max_cloud_pct": 30,
            "dry_run": True,
            "clip_polygon_geojson": _poly(),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dry_run"] is True
    assert data["preset"] == "custom"
    assert data["period"]["months"] == 2
    assert data["months_scanned"] == 2
    assert data["scenes_selected"] == 2
    assert data["jobs_scheduled"] == 0
    assert len(data["jobs"]) == 4  # 2 selected scenes × 2 indices
    assert calls and calls[0][0] == [44.0, 15.0, 44.01, 15.01]


def test_backfill_scene_job_raster_url_passes_source_guard(monkeypatch):
    """انحدار بلاغ 2026-07-04: كلّ مهامّ backfill فشلت بـHTTPException مباشرةً بعد
    بناء الـVRT، لأنّ الـVRT كُتب في /tmp (خارج UPLOAD_DIR) ومُرِّر كمسار خام
    يرفضه _safe_raster_source. العقد: الـVRT يُبنى بـout_dir=UPLOAD_DIR والمسار
    المجدول للمعالجة يجتاز حارس المصدر."""
    monkeypatch.setattr(main, "AGENT_TOKEN", "test-token")

    async def fake_search(bbox, dt_start, dt_end, max_cloud, limit):
        return {"count": 1, "items": [_scene(dt_start[:7], "A", 5.0)]}

    monkeypatch.setattr(main, "_stac_search", fake_search)

    captured: dict[str, object] = {}

    def fake_run_processing(job_id, preq):
        captured[job_id] = preq
        j = main._jobs.get(job_id) or {"job_id": job_id}
        j["status"] = main.JobStatus.completed
        main._jobs.set(job_id, j)

    monkeypatch.setattr(main, "_run_processing", fake_run_processing)

    # stac_vrt الحقيقيّ يستورد rasterio ويفتح النطاقات — بديل خفيف يحترم out_dir
    # كي يبقى الاختبار وحدويّاً ويُثبت أين تُكتب مخرجات البناء فعلاً.
    used = {}

    def fake_build_band_vrt(band_hrefs, out_dir="/tmp"):
        used["out_dir"] = out_dir
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "stac_stack_guardtest.vrt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("<VRTDataset/>")
        return path, {"red": 1, "nir": 2}

    fake_mod = types.ModuleType("stac_vrt")
    fake_mod.build_band_vrt = fake_build_band_vrt
    monkeypatch.setitem(sys.modules, "stac_vrt", fake_mod)

    client = TestClient(main.app)
    resp = client.post(
        "/v1/fields/F-guard/imagery/backfill",
        headers={"x-agent-token": "test-token", "x-tenant-id": "T-1"},
        json={
            "tenant_id": "T-1",
            "preset": "custom",
            "from_date": "2026-01-01",
            "to_date": "2026-01-31",
            "indices": ["ndvi"],
            "limit_per_month": 1,
            "max_cloud_pct": 30,
            "dry_run": False,
            "clip_polygon_geojson": _poly(),
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["jobs_scheduled"] == 1
    # TestClient ينفّذ مهامّ الخلفيّة بعد الاستجابة — الالتقاط اكتمل هنا.
    assert len(captured) == 1, "مهمّة المشهد لم تصل إلى المعالجة (فشلت قبلها؟)"
    preq = next(iter(captured.values()))
    assert used["out_dir"] == main.UPLOAD_DIR, "الـVRT يجب أن يُكتَب تحت UPLOAD_DIR"
    # جوهر الانحدار: المسار المجدول كان يُرمى 400 «مخطّط URL غير مدعوم».
    resolved = main._safe_raster_source(preq.raster_url)
    assert resolved.startswith(os.path.realpath(main.UPLOAD_DIR))


def test_backfill_requires_clip_polygon_for_new_field_geometry(monkeypatch):
    monkeypatch.setattr(main, "AGENT_TOKEN", "test-token")
    client = TestClient(main.app)
    resp = client.post(
        "/v1/fields/F-1/imagery/backfill",
        headers={"x-agent-token": "test-token", "x-tenant-id": "T-1"},
        json={"preset": "auto_12_months", "dry_run": True},
    )
    assert resp.status_code == 400
    assert "clip_polygon_geojson" in resp.text


def test_backfill_rejects_unsupported_visual_index(monkeypatch):
    monkeypatch.setattr(main, "AGENT_TOKEN", "test-token")
    client = TestClient(main.app)
    resp = client.post(
        "/v1/fields/F-1/imagery/backfill",
        headers={"x-agent-token": "test-token", "x-tenant-id": "T-1"},
        json={
            "preset": "custom",
            "from_date": "2026-01-01",
            "to_date": "2026-01-31",
            "indices": ["vari"],
            "dry_run": True,
            "clip_polygon_geojson": _poly(),
        },
    )
    assert resp.status_code == 400
    assert "غير مناسبة" in resp.text


def test_backfill_accepts_truecolor_ndwi_and_ndsi_for_persisted_map_layers(monkeypatch):
    """MapHub-visible layers must be accepted by the raster backfill contract so they can
    become persisted COGs served through /fields/{id}/tiles instead of live CDSE fallback.
    salinity is sent from the UI as backend ndsi.
    """
    monkeypatch.setattr(main, "AGENT_TOKEN", "test-token")

    async def fake_search(bbox, dt_start, dt_end, max_cloud, limit):
        return {"count": 1, "items": [_scene(dt_start[:7], "A", 5.0)]}

    monkeypatch.setattr(main, "_stac_search", fake_search)
    client = TestClient(main.app)
    resp = client.post(
        "/v1/fields/F-1/imagery/backfill",
        headers={"x-agent-token": "test-token", "x-tenant-id": "T-1"},
        json={
            "tenant_id": "T-1",
            "preset": "custom",
            "from_date": "2026-01-01",
            "to_date": "2026-01-31",
            "indices": ["truecolor", "ndwi", "ndsi"],
            "limit_per_month": 1,
            "max_cloud_pct": 30,
            "dry_run": True,
            "clip_polygon_geojson": _poly(),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["jobs_scheduled"] == 0
    assert len(data["jobs"]) == 3
    assert {j["index"] for j in data["jobs"]} == {"truecolor", "ndwi", "ndsi"}
