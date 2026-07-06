"""Behavioural: contours/soil analytics clip to the field **polygon**, not the bbox.

External review P1#5: contours + soil zones/points were computed over the bounding
rectangle, so features landed outside irregular fields. Now a `poly` (lng,lat ring)
masks the read window to the field boundary. Also covers P1#8 — sample points are
interior (not on the edge) and carry a confidence score.

Run in the raster-service suite (numpy/rasterio available).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
import soil_zones as sz
import terrain_render as tr
import tile_render
from rasterio.transform import from_bounds as t_from_bounds

_BBOX = [45.00, 16.00, 45.10, 16.10]  # حقل ~11كم
# مضلّع = النصف الغربيّ من bbox فقط (lon ≤ 45.05) — قصّ يجب أن يستبعد الشرق.
_WEST_HALF = [[45.00, 16.00], [45.05, 16.00], [45.05, 16.10], [45.00, 16.10]]


def _make_4326_raster(path: str, data: np.ndarray) -> None:
    h, w = data.shape
    profile = dict(
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=t_from_bounds(_BBOX[0], _BBOX[1], _BBOX[2], _BBOX[3], w, h),
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)


def test_read_field_window_masks_outside_polygon(tmp_path: Path):
    data = np.ones((40, 40)) * 100.0
    p = str(tmp_path / "r.tif")
    _make_4326_raster(p, data)
    with rasterio.open(p) as src:
        arr, _sx, _sy = tile_render.read_field_window(src, _BBOX, poly_lonlat=_WEST_HALF)
    # النصف الغربيّ فيه بيانات، الشرقيّ NaN (خارج المضلّع).
    finite = np.isfinite(arr)
    left = finite[:, : arr.shape[1] // 2].sum()
    right = finite[:, arr.shape[1] // 2 :].sum()
    assert left > 0
    assert right < left * 0.15, f"القصّ لم يستبعد الشرق: left={left} right={right}"


def test_soil_points_stay_inside_polygon(tmp_path: Path, monkeypatch):
    d = tmp_path / "soil"
    d.mkdir()
    monkeypatch.setenv("SOILGRIDS_DIR", str(d))
    rows, cols = 40, 40
    grad = np.linspace(0, 1, cols)[None, :].repeat(rows, axis=0)
    _make_4326_raster(str(d / "clay_0-5cm.tif"), 200 + 200 * grad)
    _make_4326_raster(str(d / "sand_0-5cm.tif"), 500 - 200 * grad.T)

    pts = sz.compute_soil_sampling_points(_BBOX, depth="0-5cm", n_zones=2, poly=_WEST_HALF)
    assert pts["computed"] is True and pts["features"]
    for feat in pts["features"]:
        lon, _lat = feat["geometry"]["coordinates"]
        assert lon <= 45.051, f"نقطة عيّنة خارج المضلّع (شرق): {lon}"
        props = feat["properties"]
        # P1#8: نقطة داخليّة + ثقة رقميّة + عدد بكسلات.
        assert props["placement"] in ("interior", "zone")
        assert 0.0 <= props["confidence_score"] <= 1.0
        assert props["zone_pixels"] >= 3


def test_contours_clip_to_polygon(tmp_path: Path):
    dem = np.linspace(100, 300, 50 * 50).reshape(50, 50)
    p = str(tmp_path / "dem.tif")
    _make_4326_raster(p, dem)
    out = tr.compute_field_contours(p, _BBOX, interval_m=20.0, poly=_WEST_HALF)
    assert out["computed"] is True and out["features"]
    for feat in out["features"]:
        for line in feat["geometry"]["coordinates"]:
            for lon, _lat in line:
                assert lon <= 45.055, f"كنتور خارج المضلّع (شرق): {lon}"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
