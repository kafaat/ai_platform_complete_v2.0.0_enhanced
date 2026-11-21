"""Normalized-difference indices over two zero bands are no-data, not 0.0.

The shared kernel `band_math.normalized_difference` used to divide by a 1e-10 epsilon,
so a pixel whose two bands were both 0 published a valid 0.0 ("no vegetation"). The CDSE
native path computes the raw expression and gives NaN there. A zero denominator is now
invalid, like a negative band. Only (0, 0) changes; every other non-negative finite pair
keeps its value.

The raster-service suite pins this per index; this test keeps the contract in the unit
gate that measures coverage, and covers the two consumers that inherit it (DBSI, FAPAR).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.unit

RASTER = Path(__file__).resolve().parents[1] / "services" / "raster-service"
if str(RASTER) not in sys.path:
    sys.path.insert(0, str(RASTER))

import band_math  # noqa: E402
import soil_indices  # noqa: E402

_ND = {
    "normalized_difference": lambda a, b: band_math.normalized_difference(a, b, np),
    "ndvi": lambda a, b: band_math.ndvi(b, a, np),  # ndvi(red, nir)
    "ndre": lambda a, b: band_math.ndre(a, b, np),
    "moisture": lambda a, b: band_math.moisture(a, b, np),
    "ndti": lambda a, b: soil_indices.compute_ndti(a, b, np),
    "ndsi": lambda a, b: soil_indices.compute_ndsi(a, b, np),
}


@pytest.mark.parametrize("name", sorted(_ND))
def test_two_zero_bands_are_nan_and_ordinary_pixels_keep_their_value(name):
    a = np.array([0.0, 0.6, 0.2, 0.0, 0.3])
    b = np.array([0.0, 0.2, 0.6, 0.4, 0.0])
    out = _ND[name](a, b)
    assert np.isnan(out[0]), f"{name}: (0, 0) must be no-data, got {out[0]}"
    assert np.allclose(out[1:], (a[1:] - b[1:]) / (a[1:] + b[1:]))
    # One band zero is a real value, not no-data.
    assert out[3] == pytest.approx(-1.0) and out[4] == pytest.approx(1.0)


def test_kernel_has_no_epsilon_helper_left():
    assert not hasattr(band_math, "_eps")


def test_dbsi_inherits_no_data_from_either_normalized_difference():
    green = np.array([0.0, 0.2, 0.2])
    swir1 = np.array([0.0, 0.4, 0.4])
    ndvi = band_math.ndvi(np.array([0.1, 0.0, 0.1]), np.array([0.5, 0.0, 0.5]), np)
    out = soil_indices.compute_dbsi(green, swir1, ndvi, np)
    assert np.isnan(out[0])  # green = swir1 = 0
    assert np.isnan(out[1])  # red = nir = 0
    assert np.isfinite(out[2])


def test_fapar_over_two_zero_bands_stays_no_data_through_clip():
    # raster_pixel_processing: fapar = clip(1.24 * ndvi - 0.168, 0, 1). It used to be 0 here.
    ndvi = band_math.ndvi(np.array([0.0, 0.1]), np.array([0.0, 0.5]), np)
    fapar = np.clip(1.24 * ndvi - 0.168, 0, 1)
    assert np.isnan(fapar[0])
    assert 0.0 <= fapar[1] <= 1.0
