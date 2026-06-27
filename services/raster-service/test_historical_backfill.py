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
    assert data["default_preset"] == "auto_12_months"
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
