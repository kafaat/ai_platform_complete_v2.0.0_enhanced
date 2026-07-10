from __future__ import annotations

import numpy as np
import raster_topographic_qa as tq


def test_topographic_qa_is_honest_without_dem():
    out = tq.build_topographic_qa(dem_configured=False)
    assert out["schema"] == "sahool.raster_topographic_qa/1"
    assert out["available"] is False
    assert out["fabricated_topographic_mask"] is False
    assert "dem_not_configured_for_topographic_qa" in out["warnings"]


def test_topographic_qa_available_only_with_aligned_dem_and_real_risk():
    out = tq.build_topographic_qa(
        dem_configured=True,
        dem_aligned=True,
        terrain_shadow_risk_pct=12.5,
        slope_risk_pct=4.0,
        hillshade_available=True,
        sun_geometry_available=True,
        sources=["FIELD_DEM_PATH", "sun_geometry"],
    )
    assert out["available"] is True
    assert out["topographic_qa_applied"] is True
    assert out["terrain_shadow_risk_pct"] == 12.5
    assert out["slope_risk_pct"] == 4.0
    assert out["sources"] == ["FIELD_DEM_PATH", "sun_geometry"]


def test_topographic_risk_from_dem_computes_slope_without_sun():
    dem = np.tile(np.arange(20, dtype="float32"), (20, 1)) * 2.0
    risk = tq.compute_topographic_risk_from_dem(dem, pixel_size_m=1.0)
    assert risk["slope_risk_pct"] is not None
    assert risk["slope_risk_pct"] > 0
    assert risk["terrain_shadow_risk_pct"] is None
    assert risk["hillshade_available"] is False
    assert "sun_geometry_unavailable_for_terrain_shadow_model" in risk["warnings"]


def test_topographic_risk_from_dem_computes_shadow_with_sun():
    dem = np.tile(np.arange(30, dtype="float32"), (30, 1)) * 5.0
    risk = tq.compute_topographic_risk_from_dem(
        dem,
        pixel_size_m=1.0,
        sun_azimuth_deg=90.0,
        sun_altitude_deg=20.0,
    )
    assert risk["hillshade_available"] is True
    assert risk["sun_geometry_available"] is True
    assert risk["terrain_shadow_risk_pct"] is not None
    assert 0.0 <= risk["terrain_shadow_risk_pct"] <= 100.0
    assert risk["slope_risk_pct"] is not None


def test_topographic_qa_from_aligned_dem_array_is_not_fabricated():
    dem = np.tile(np.arange(15, dtype="float32"), (15, 1))
    out = tq.build_topographic_qa_from_dem_array(
        dem,
        pixel_size_m=1.0,
        sun_azimuth_deg=135.0,
        sun_altitude_deg=35.0,
        sources=["FIELD_DEM_PATH", "indicator_grid_dem_alignment"],
    )
    assert out["schema"] == "sahool.raster_topographic_qa/1"
    assert out["dem_aligned"] is True
    assert out["available"] is True
    assert out["topographic_qa_applied"] is True
    assert out["fabricated_topographic_mask"] is False
    assert out["method"] in {"dem_hillshade_slope", "dem_cast_shadow_hillshade_slope"}
    assert "indicator_grid_dem_alignment" in out["sources"]


def test_cast_shadow_mask_detects_blocked_pixels():
    dem = np.zeros((30, 30), dtype="float32")
    dem[5, :] = 100.0
    cast = tq.compute_cast_shadow_mask_from_dem(
        dem,
        pixel_size_m=1.0,
        sun_azimuth_deg=0.0,
        sun_altitude_deg=15.0,
        max_steps=20,
    )
    assert cast["cast_shadow_available"] is True
    assert cast["cast_shadow_risk_pct"] is not None
    assert cast["cast_shadow_risk_pct"] > 0.0
    assert cast["cast_shadow_max_steps"] == 20


def test_topographic_qa_from_aligned_dem_array_includes_cast_shadow_contract():
    dem = np.zeros((30, 30), dtype="float32")
    dem[5, :] = 100.0
    out = tq.build_topographic_qa_from_dem_array(
        dem,
        pixel_size_m=1.0,
        sun_azimuth_deg=0.0,
        sun_altitude_deg=15.0,
        sources=["FIELD_DEM_PATH", "indicator_grid_dem_alignment"],
    )
    assert out["cast_shadow_available"] is True
    assert out["cast_shadow_risk_pct"] is not None
    assert out["method"] == "dem_cast_shadow_hillshade_slope"
    assert out["fabricated_topographic_mask"] is False


def test_topographic_indicator_helper_fails_closed_on_dem_alignment_error(tmp_path, monkeypatch):
    """Alignment/open failure must degrade gracefully without fabricating terrain masks."""
    import raster_pixel_processing as rpp

    bad_dem = tmp_path / "bad_dem.tif"
    bad_dem.write_text("not a geotiff", encoding="utf-8")
    monkeypatch.setenv("FIELD_DEM_PATH", str(bad_dem))

    class Transform:
        a = 10.0

    out = rpp._topographic_qa_for_indicator(
        ctx=object(),
        req=None,
        raster_crs="EPSG:4326",
        raster_transform=Transform(),
        raster_shape=(8, 8),
    )
    assert out["available"] is False
    assert out["dem_configured"] is True
    assert out["dem_aligned"] is False
    assert out["fabricated_topographic_mask"] is False
    assert any("dem_topographic_qa_failed" in str(w) for w in out["warnings"])


def test_topographic_indicator_helper_fails_closed_without_field_dem(monkeypatch):
    """Indicator path must fail closed when FIELD_DEM_PATH is absent."""
    import raster_pixel_processing as rpp

    monkeypatch.delenv("FIELD_DEM_PATH", raising=False)

    class Request:
        sun_azimuth_deg = 120.0
        sun_altitude_deg = 25.0

    class Transform:
        a = 10.0

    out = rpp._topographic_qa_for_indicator(
        ctx=object(),
        req=Request(),
        raster_crs="EPSG:32638",
        raster_transform=Transform(),
        raster_shape=(8, 8),
    )
    assert out["available"] is False
    assert out["dem_configured"] is False
    assert out["dem_aligned"] is False
    assert out["sun_geometry_available"] is True
    assert out["fabricated_topographic_mask"] is False
    assert "dem_not_configured_for_topographic_qa" in out["warnings"]


def test_topographic_qa_from_aligned_dem_array_partial_without_sun_geometry():
    """Aligned DEM without sun geometry should compute slope but not shadow/cast-shadow."""
    dem = np.tile(np.arange(20, dtype="float32"), (20, 1)) * 3.0
    out = tq.build_topographic_qa_from_dem_array(
        dem,
        pixel_size_m=1.0,
        sources=["FIELD_DEM_PATH", "indicator_grid_dem_alignment"],
    )
    assert out["dem_configured"] is True
    assert out["dem_aligned"] is True
    assert out["available"] is True
    assert out["slope_risk_pct"] is not None
    assert out["terrain_shadow_risk_pct"] is None
    assert out["cast_shadow_available"] is False
    assert out["cast_shadow_risk_pct"] is None
    assert out["hillshade_available"] is False
    assert out["sun_geometry_available"] is False
    assert out["fabricated_topographic_mask"] is False
    assert "sun_geometry_unavailable_for_terrain_shadow_model" in out["warnings"]
