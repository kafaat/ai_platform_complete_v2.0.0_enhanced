import sys
import types

import main
import scene_policy
from fastapi.testclient import TestClient
from routers import fields as field_routes


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

    monkeypatch.setattr(field_routes, "_stac_search", fake_search)
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


def test_backfill_element84_scene_job_is_contained_before_vrt_and_processing(monkeypatch):
    """مشهد Element84 (ذو ``bands_urls``) محجوبٌ عبر نقطة HTTP الحقيقيّة: ``radiometry_containment``.

    كان هذا الاختبار يُثبت انحدار 2026-07-04 (الـVRT يُكتب تحت ``UPLOAD_DIR`` فيجتاز
    ``_safe_raster_source``). المسار محجوبٌ الآن قبل بناء الـVRT — المقياس والمحاذاة وNoData
    غير محسومة — فالعقد: المهمّة تُجدوَل وتُسجَّل ``failed`` بـ``radiometry_unresolved``
    و``retryable:false``، بلا VRT ولا معالجة. **عند رفع الاحتواء** يُستعاد شرطُ ``UPLOAD_DIR``
    ضمن عقد التطبيع (درسُ البلاغ باقٍ: مسارٌ خارج المجلّد المسموح يُرمى 400).
    """
    monkeypatch.setattr(main, "AGENT_TOKEN", "test-token")

    async def fake_search(bbox, dt_start, dt_end, max_cloud, limit):
        return {"count": 1, "items": [_scene(dt_start[:7], "A", 5.0)]}

    monkeypatch.setattr(field_routes, "_stac_search", fake_search)

    def _trap(*_a, **_k):
        raise AssertionError("بلغ الطلبُ المحجوب مرحلةً لاحقة للرفض")

    monkeypatch.setattr(field_routes, "_run_processing", _trap)
    fake_mod = types.ModuleType("stac_vrt")
    fake_mod.build_band_vrt = _trap
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
    (job,) = resp.json()["jobs"]
    # TestClient ينفّذ مهامّ الخلفيّة بعد الاستجابة — الحالة النهائيّة مكتوبة هنا.
    stored = main._jobs.get(job["job_id"])
    assert stored["status"] == main.JobStatus.failed
    assert stored["error_message"] == "radiometry_unresolved"
    assert stored["retryable"] is False
    assert stored["error_detail"]["entry_point"] == "historical_backfill"


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
            "indices": ["lst"],
            "dry_run": True,
            "clip_polygon_geojson": _poly(),
        },
    )
    assert resp.status_code == 400
    assert "غير مناسبة" in resp.text


def test_backfill_accepts_top20_persisted_map_layers(monkeypatch):
    """MapHub-visible layers must be accepted by the raster backfill contract so they can
    become persisted COGs served through /fields/{id}/tiles instead of live CDSE fallback.
    salinity is sent from the UI as backend ndsi.
    """
    monkeypatch.setattr(main, "AGENT_TOKEN", "test-token")

    async def fake_search(bbox, dt_start, dt_end, max_cloud, limit):
        return {"count": 1, "items": [_scene(dt_start[:7], "A", 5.0)]}

    monkeypatch.setattr(field_routes, "_stac_search", fake_search)
    client = TestClient(main.app)
    resp = client.post(
        "/v1/fields/F-1/imagery/backfill",
        headers={"x-agent-token": "test-token", "x-tenant-id": "T-1"},
        json={
            "tenant_id": "T-1",
            "preset": "custom",
            "from_date": "2026-01-01",
            "to_date": "2026-01-31",
            "indices": [
                "truecolor",
                "ndvi",
                "ndmi",
                "savi",
                "evi",
                "gndvi",
                "ndre",
                "reci",
                "gci",
                "arvi",
                "sipi",
                "nbr",
                "ccci",
                "vari",
                "gli",
                "bsi",
                "msi",
                "msavi",
                "ndwi",
                "ndsi",
            ],
            "limit_per_month": 1,
            "max_cloud_pct": 30,
            "dry_run": True,
            "clip_polygon_geojson": _poly(),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["jobs_scheduled"] == 0
    assert len(data["jobs"]) == 20
    assert {j["index"] for j in data["jobs"]} == {
        "truecolor",
        "ndvi",
        "ndmi",
        "savi",
        "evi",
        "gndvi",
        "ndre",
        "reci",
        "gci",
        "arvi",
        "sipi",
        "nbr",
        "ccci",
        "vari",
        "gli",
        "bsi",
        "msi",
        "msavi",
        "ndwi",
        "ndsi",
    }


def test_ndvi_backfill_policy_accepts_50pct_cloud_and_enforces_spacing():
    scenes = [
        {"item_id": "too-cloudy", "datetime": "2026-07-01T08:00:00Z", "cloud_cover_pct": 55},
        {"item_id": "day1", "datetime": "2026-07-01T08:00:00Z", "cloud_cover_pct": 20},
        {"item_id": "day2-too-close", "datetime": "2026-07-02T08:00:00Z", "cloud_cover_pct": 5},
        {"item_id": "day4", "datetime": "2026-07-04T08:00:00Z", "cloud_cover_pct": 50},
        {"item_id": "day8", "datetime": "2026-07-08T08:00:00Z", "cloud_cover_pct": 30},
    ]
    selected = scene_policy.select_backfill_scenes_by_policy(
        scenes,
        indices=["ndvi"],
        max_cloud_pct=50,
        limit=8,
    )
    ids = [s["item_id"] for s in selected]
    assert "too-cloudy" not in ids
    assert "day4" in ids  # cloud=50 => clear=50 is accepted by policy
    assert all((s.get("clear_pct") is None or s["clear_pct"] >= 50) for s in selected)
    assert all(s.get("quality_label") in {"high", "medium"} for s in selected)


def test_available_dates_cloud_quality_metadata(monkeypatch):
    monkeypatch.setattr(main, "AGENT_TOKEN", "test-token")
    main._field_layers["F-quality"] = ["L-quality"]
    main._layers["L-quality"] = {
        "field_id": "F-quality",
        "index": "ndvi",
        "cog_url": "file:///tmp/fake.tif",
        "acquisition_date": "2026-07-05T07:35:29Z",
        "cloud_pct": 50,
        "provenance": {"scene_id": "S2_TEST"},
    }
    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/F-quality/available-dates?index=ndvi",
        headers={"x-agent-token": "test-token", "x-tenant-id": "T-1"},
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["dates"][0]
    assert item["cloud_pct"] == 50
    assert item["clear_pct"] == 50
    assert item["quality_label"] == "medium"


def test_available_dates_merges_aoi_quality_and_applies_one_timeline_window(monkeypatch):
    """Route contract survives extraction: tenant reads, AOI precedence, dedup and cutoff."""
    import asyncio
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import db_persist
    from routers import fields

    tenant = "00000000-0000-4000-8000-000000000001"
    authorized = []

    async def authorize(field_id, *, hide_existence):
        authorized.append((field_id, hide_existence))

    async def stored(field_id, *, tenant_id, indices, limit):
        assert field_id == "F-merge" and tenant_id == tenant and indices == ["ndvi"]
        return [
            {
                "date": "2026-10-15",
                "index_name": "ndvi",
                "cloud_pct": 90,
                "aoi_cloud_pct": 5,
                "scene_id": "stored-scene",
                "has_cog": True,
            },
            {"date": "2026-08-01", "index_name": "ndvi", "cloud_pct": 0, "has_cog": True},
        ]

    async def geometry(field_id, tenant_id):
        assert field_id == "F-merge" and tenant_id == tenant
        return {"type": "Polygon", "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 15]]]}

    async def search(*args, **kwargs):
        return {
            "items": [
                {"datetime": "2026-10-15T07:30:00Z", "cloud_cover_pct": 95, "item_id": "provider"},
                {"datetime": "2026-10-14T07:30:00Z", "cloud_cover_pct": 10, "item_id": "new"},
            ]
        }

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 16, tzinfo=UTC)

    monkeypatch.setattr(fields, "datetime", Clock)
    monkeypatch.setattr(fields, "_require_field_tenant", authorize)
    monkeypatch.setattr(fields, "_REQ_TENANT", SimpleNamespace(get=lambda: tenant))
    monkeypatch.setattr(fields, "_field_layers", {})
    monkeypatch.setattr(fields, "_stac_search", search)
    monkeypatch.setattr(fields, "_month_windows", lambda start, end: [(start, end)])
    monkeypatch.setattr(db_persist, "list_available_asset_dates", stored)
    monkeypatch.setattr(db_persist, "fetch_field_geometry", geometry)
    result = asyncio.run(
        fields.field_available_dates(
            "F-merge", index="ndvi", limit=100, include_provider=True, months=1
        )
    )
    assert authorized == [("F-merge", True)]
    assert "provider_dates_error" not in result
    assert [item["date"] for item in result["dates"]] == ["2026-10-15", "2026-10-14"]
    first, second = result["dates"]
    assert first["scene_cloud_pct"] == first["cloud_pct"] == 90
    assert first["aoi_cloud_pct"] == 5 and first["clear_pct"] == 95
    assert first["quality_label"] == "high" and first["has_cog"] is True
    assert first["scene_id"] == "stored-scene"
    # T1 (acq-provenance): وقت عنصر الكتالوج "provider" لا يُلصَق بمشهد "stored-scene"؛
    # الأصل المُدَام بلا وقت التقاط مُسجَّل ⇒ None صادقة، والمساهمان معدودان.
    assert first["acquisition_datetime"] is None
    assert first["contributors"] == 2
    assert second["has_cog"] is False and second["aoi_cloud_pct"] is None
