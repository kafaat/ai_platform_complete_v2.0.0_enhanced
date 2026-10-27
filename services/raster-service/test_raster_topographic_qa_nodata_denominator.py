"""PROC-04 regression: nodata must not dilute topographic risk percentages.

Each risk ratio is count(valid supported risk pixels) / count(valid supported
pixels). Padding the same DEM patch with a nodata (NaN) frame changes no
physical terrain, so it must not change any reported risk percentage.
"""

from __future__ import annotations

import numpy as np
import pytest
import raster_topographic_qa as tq


def _pad_with_nodata(patch: np.ndarray, margin: int) -> np.ndarray:
    h, w = patch.shape
    framed = np.full((h + 2 * margin, w + 2 * margin), np.nan, dtype="float32")
    framed[margin : margin + h, margin : margin + w] = patch
    return framed


def test_slope_risk_is_invariant_to_nodata_padding():
    # Audit witness: an 8x8 steep ramp is 100% slope risk on its own, but was
    # only 14.0625% once embedded in a 16x16 NaN frame (36 supported / 256).
    patch = np.tile(np.arange(8, dtype="float32"), (8, 1))
    alone = tq.compute_topographic_risk_from_dem(patch, pixel_size_m=1.0)
    framed = tq.compute_topographic_risk_from_dem(_pad_with_nodata(patch, 4), pixel_size_m=1.0)
    assert alone["slope_risk_pct"] == pytest.approx(100.0)
    assert framed["slope_risk_pct"] == pytest.approx(alone["slope_risk_pct"])
    # The coverage ratio still honestly reports how much of the grid is DEM.
    assert framed["valid_dem_pixel_ratio"] == pytest.approx(0.25)


def test_hillshade_shadow_risk_is_invariant_to_nodata_padding():
    patch = np.tile(np.arange(30, dtype="float32"), (30, 1)) * 5.0
    kwargs = dict(
        pixel_size_m=1.0,
        sun_azimuth_deg=90.0,
        sun_altitude_deg=20.0,
        cast_shadow_enabled=False,
    )
    alone = tq.compute_topographic_risk_from_dem(patch, **kwargs)
    framed = tq.compute_topographic_risk_from_dem(_pad_with_nodata(patch, 10), **kwargs)
    assert alone["terrain_shadow_risk_pct"] == pytest.approx(100.0)
    assert framed["terrain_shadow_risk_pct"] == pytest.approx(alone["terrain_shadow_risk_pct"])


def test_cast_shadow_risk_is_invariant_to_nodata_padding():
    patch = np.zeros((30, 30), dtype="float32")
    patch[5, :] = 100.0
    kwargs = dict(pixel_size_m=1.0, sun_azimuth_deg=0.0, sun_altitude_deg=15.0, max_steps=20)
    alone = tq.compute_cast_shadow_mask_from_dem(patch, **kwargs)
    framed = tq.compute_cast_shadow_mask_from_dem(_pad_with_nodata(patch, 10), **kwargs)
    assert alone["cast_shadow_risk_pct"] > 0.0
    assert framed["cast_shadow_risk_pct"] == pytest.approx(alone["cast_shadow_risk_pct"])


def test_topographic_qa_envelope_is_invariant_to_nodata_padding():
    patch = np.zeros((30, 30), dtype="float32")
    patch[5, :] = 100.0
    kwargs = dict(pixel_size_m=1.0, sun_azimuth_deg=0.0, sun_altitude_deg=15.0)
    alone = tq.build_topographic_qa_from_dem_array(patch, **kwargs)
    framed = tq.build_topographic_qa_from_dem_array(_pad_with_nodata(patch, 10), **kwargs)
    for key in ("terrain_shadow_risk_pct", "cast_shadow_risk_pct"):
        assert framed[key] == pytest.approx(alone[key]), key


def test_slope_risk_without_gradient_support_is_unavailable_not_zero():
    # Isolated valid DEM cells (checkerboard of nodata) have no finite
    # neighbour on either axis, so no slope can be measured anywhere. That is
    # "insufficient support", not "0% risk".
    dem = np.full((8, 8), np.nan, dtype="float32")
    dem[::2, ::2] = 50.0
    risk = tq.compute_topographic_risk_from_dem(dem, pixel_size_m=1.0)
    assert risk["slope_risk_pct"] is None
    assert "dem_gradient_support_insufficient" in risk["warnings"]
