from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "services/raster-service/main.py").read_text(encoding="utf-8")
TILE = (ROOT / "services/raster-service/tile_render.py").read_text(encoding="utf-8")
FIELDS = (ROOT / "services/sahool-platform/api/routers/fields.py").read_text(encoding="utf-8")
DBP = (ROOT / "services/raster-service/db_persist.py").read_text(encoding="utf-8")


def test_raster_sensitive_operational_routes_require_agent_token():
    for route in (
        '@app.get("/storage/stats")',
        '@app.get("/offline/packs")',
        '@app.get("/offline/packs/{pack_name}")',
    ):
        i = MAIN.index(route)
        body = MAIN[i : i + 650]
        assert "x_agent_token" in body
        assert "_require_service_token(x_agent_token)" in body


def test_raster_service_token_uses_constant_time_compare_digest():
    i = MAIN.index("def _require_service_token")
    body = MAIN[i : i + 450]
    assert "hmac.compare_digest" in body
    assert "x_agent_token != AGENT_TOKEN" not in body


def test_layer_tenant_authorization_has_db_fallback():
    assert "async def _require_layer_tenant_authorized" in MAIN
    body = MAIN[
        MAIN.index("async def _require_layer_tenant_authorized") : MAIN.index("def _public_cog_url")
    ]
    assert "db_persist.layer_owner_tenant" in body
    assert "OwnerLookupUnavailable" in body
    assert "fail" in body.lower() or "503" in body
    assert "async def layer_owner_tenant" in DBP


def test_pixel_endpoint_exists_and_checks_bounds_and_real_cog():
    assert '@app.get("/v1/fields/{field_id}/pixel")' in MAIN
    body = MAIN[
        MAIN.index('@app.get("/v1/fields/{field_id}/pixel")') : MAIN.index(
            "class PrescriptionRequest"
        )
    ]
    assert "await _require_field_tenant" in body
    assert "_resolve_field_layer" in body
    assert "src.sample" in body
    assert "النقطة خارج" in body


def test_tile_renderer_uses_windowed_dataset_reproject_not_full_read():
    assert "rasterio.band(src, 1)" in TILE
    assert "src_arr = src.read(1)" not in TILE


def test_field_detail_and_delete_have_explicit_tenant_filter():
    assert "FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid" in FIELDS
    assert (
        "SELECT field_id, name, crop, farm_id FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid"
        in FIELDS
    )


def test_cloud_mask_missing_scl_is_not_silent_and_cloud_pct_is_recorded():
    assert "cloud mask requested but SCL band is missing" in MAIN
    assert '"cloud_pct": cloud_pct' in MAIN
    assert '"cloud_mask_applied"' in MAIN


def test_pixel_endpoint_returns_quality_confidence_not_none():
    body = MAIN[
        MAIN.index('@app.get("/v1/fields/{field_id}/pixel")') : MAIN.index(
            "class PrescriptionRequest"
        )
    ]
    assert "quality = _pixel_quality" in body
    assert '"confidence": quality["confidence"]' in body
    assert '"quality": quality["quality"]' in body
    assert '"cloud_pct": quality.get("cloud_pct")' in body
    assert '"confidence": None' not in body


def test_field_aoi_cloud_pct_quality_persisted_and_rehydrated():
    assert "def _quality_from_cloud_pct" in MAIN
    assert '"confidence": quality["confidence"]' in MAIN
    assert '"quality": quality["quality"]' in MAIN
    assert '"cloud_pct": stats.get("cloud_pct")' in MAIN
    assert '"cloud_mask_applied": stats.get("cloud_mask_applied")' in MAIN
    assert "provenance #>> '{stats,confidence}' AS confidence" in DBP
    assert '"cloud_pct": float(row["cloud_pct"])' in DBP


def test_indicator_grid_exposes_layer_quality_metadata():
    body = MAIN[MAIN.index("def _grid_from_cog") : MAIN.index("async def _resolve_field_layer")]
    assert '"cloud_pct": layer.get("cloud_pct")' in body
    assert '"confidence": layer.get("confidence")' in body
    assert '"quality": layer.get("quality")' in body
