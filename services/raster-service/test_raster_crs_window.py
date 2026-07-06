"""Behavioural: terrain/soil window-read paths are CRS-correct on **projected** rasters.

External review flagged that the vector/summary paths (compute_field_terrain,
compute_field_contours, read_property_bbox, soil zones/points) built a read window from
lon/lat bounds against `src.transform` directly — correct only when the raster is
EPSG:4326. On a projected raster (UTM DEM, SoilGrids Homolosine) the window is wrong and
GeoJSON output lands in projection metres. These prove the shared `read_field_window`
helper reprojects bounds and caps size, and that vector outputs come back in lon/lat.

Not collected by the CI unit tier (testpaths = tests_v9); run locally / in the
raster-service suite with numpy/rasterio.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
import soil_render as sr
import soil_zones as sz
import terrain_analysis as ta
import terrain_render as tr
import tile_render
from rasterio.transform import from_bounds as t_from_bounds
from rasterio.warp import transform_bounds

_UTM = "EPSG:32638"  # UTM zone 38N — يغطّي شرق اليمن (~lon 45)
_LL_BBOX = [45.00, 16.00, 45.02, 16.02]  # حقل ~2كم في lon/lat


def _make_projected_raster(path: str, data: np.ndarray, nodata=None) -> None:
    """يكتب GeoTIFF مُسقَطاً (UTM) يغطّي _LL_BBOX — CRS غير EPSG:4326 عمداً."""
    h, w = data.shape
    minx, miny, maxx, maxy = transform_bounds("EPSG:4326", _UTM, *_LL_BBOX)
    profile = dict(
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs=_UTM,
        transform=t_from_bounds(minx, miny, maxx, maxy, w, h),
    )
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)


def _in_bbox(lon: float, lat: float) -> bool:
    eps = 1e-4
    return (_LL_BBOX[0] - eps) <= lon <= (_LL_BBOX[2] + eps) and (
        (_LL_BBOX[1] - eps) <= lat <= (_LL_BBOX[3] + eps)
    )


def test_read_field_window_reprojects_and_caps(tmp_path: Path):
    # تدرّج معروف؛ نافذة lon/lat على raster مُسقَط يجب أن تُعيد بيانات (لا فراغ).
    data = np.linspace(100, 300, 50 * 50).reshape(50, 50)
    p = str(tmp_path / "utm.tif")
    _make_projected_raster(p, data)
    with rasterio.open(p) as src:
        res = tile_render.read_field_window(src, _LL_BBOX)
        assert res is not None
        arr, sx, sy = res
        assert arr.size > 0 and np.isfinite(arr).any()
        assert sx == 1.0 and sy == 1.0  # نافذة صغيرة ⇒ بلا تخفيض
        # سقف الحجم: max_dim صغير ⇒ تخفيض عيّنة (scale > 1) وأبعاد مسقوفة.
        capped = tile_render.read_field_window(src, _LL_BBOX, max_dim=8)
        assert capped is not None
        arr2, sx2, sy2 = capped
        assert arr2.shape[0] <= 8 and arr2.shape[1] <= 8
        assert sx2 > 1.0 and sy2 > 1.0


def test_terrain_projected_dem_computes_and_contours_in_lonlat(tmp_path: Path):
    # DEM مُسقَط بتدرّج ارتفاع 100..300م ⇒ إحصاءات محسوبة + كنتور بإحداثيّات lon/lat.
    dem = np.linspace(100, 300, 60 * 60).reshape(60, 60)
    p = str(tmp_path / "dem_utm.tif")
    _make_projected_raster(p, dem, nodata=-32768.0)

    terr = ta.compute_field_terrain(p, _LL_BBOX)
    assert terr.get("computed") is True, terr
    assert 90 <= terr["elevation_m"]["min"] <= 310
    assert 90 <= terr["elevation_m"]["max"] <= 310

    cont = tr.compute_field_contours(p, _LL_BBOX, interval_m=20.0)
    assert cont["computed"] is True
    assert cont["features"], "لا كنتور رغم تدرّج ارتفاع واضح"
    checked = 0
    for feat in cont["features"]:
        for line in feat["geometry"]["coordinates"]:
            for lon, lat in line:
                assert _in_bbox(lon, lat), f"إحداثيّة كنتور خارج bbox (CRS خاطئ): {lon},{lat}"
                checked += 1
    assert checked > 0


def test_soil_projected_zones_and_points_in_lonlat(tmp_path: Path, monkeypatch):
    # مصدر SoilGrids مُسقَط (UTM): clay/sand بتدرّج ⇒ مناطق ونقاط بإحداثيّات lon/lat.
    d = tmp_path / "soil"
    d.mkdir()
    monkeypatch.setenv("SOILGRIDS_DIR", str(d))
    # clay/sand مخزّنان ×10 (اصطلاح SoilGrids)؛ تدرّجان متعامدان ⇒ مناطق قابلة للفصل.
    rows, cols = 50, 50
    grad = np.linspace(0, 1, cols)[None, :].repeat(rows, axis=0)
    clay = (200 + 200 * grad).astype("float32")  # طين 20..40٪
    sand = (500 - 200 * grad.T).astype("float32")  # رمل 50..30٪
    _make_projected_raster(str(d / "clay_0-5cm.tif"), clay)
    _make_projected_raster(str(d / "sand_0-5cm.tif"), sand)
    assert sr.is_source_configured()

    zones = sz.compute_soil_sampling_zones(_LL_BBOX, depth="0-5cm", n_zones=2)
    assert zones["computed"] is True, zones
    assert zones["features"], "لا مناطق تربة رغم تدرّج واضح"
    for feat in zones["features"]:
        for poly in feat["geometry"]["coordinates"]:  # MultiPolygon
            for ring in poly:
                for lon, lat in ring:
                    assert _in_bbox(lon, lat), f"رأس منطقة خارج bbox (CRS خاطئ): {lon},{lat}"

    pts = sz.compute_soil_sampling_points(_LL_BBOX, depth="0-5cm", n_zones=2)
    assert pts["computed"] is True and pts["features"]
    for feat in pts["features"]:
        lon, lat = feat["geometry"]["coordinates"]
        assert _in_bbox(lon, lat), f"نقطة عيّنة خارج bbox (CRS خاطئ): {lon},{lat}"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
