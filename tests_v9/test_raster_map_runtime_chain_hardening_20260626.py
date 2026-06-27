from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_maplibre_indicator_layer_refreshes_when_imagery_date_changes():
    src = read("frontend/src/components/maphub/HubMapGL.tsx")
    assert "imageryDate" in src
    assert (
        "[indicatorId, selectedId, indicatorOpacity, fields, tenantId, imageryTs, imageryDate]"
        in src
    )


def test_raster_tile_cache_key_accepts_cache_buster_version():
    src = read("services/raster-service/main.py")
    assert "v: str | None = Query(None)" in src
    assert "_tile_cache_key(field_id, index, date, z, x, y, tenant, v=v)" in src


def test_cdse_processing_binds_real_acquisition_date_before_persisting():
    src = read("services/raster-service/main.py")
    assert "client.search_scenes(" in src
    assert 'capture_datetime = best.get("datetime")' in src
    assert "capture_datetime=capture_datetime" in src
    assert 'scene_id=f"{scene_id}:{ind}"' in src


def test_available_dates_route_exists_on_platform_and_raster():
    raster = read("services/raster-service/main.py")
    fields = read("services/sahool-platform/api/routers/fields.py")
    api = read("frontend/src/services/api.ts")
    assert '@app.get("/v1/fields/{field_id}/available-dates")' in raster
    assert '@router.get("/api/v1/fields/{field_id}/available-dates")' in fields
    assert "fetchFieldImageryAvailableDates" in api


def test_manual_refresh_can_request_specific_scene_date():
    fields = read("services/sahool-platform/api/routers/fields.py")
    automation = read("services/sahool-platform/api/imagery_automation.py")
    frontend = read("frontend/src/sections/MapHub.tsx")
    assert "class FieldImageryRefreshRequest" in fields
    assert "date=(req.date[:10] if req and req.date else None)" in fields
    assert 'date_from=f"{date[:10]}T00:00:00Z" if date else None' in automation
    assert "refreshFieldImagery(fieldId, selectedImageryDate)" in frontend
