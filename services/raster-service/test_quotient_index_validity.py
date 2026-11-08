"""Quotient and soil indices must mask invalid pixels, not publish ±1e7..1e9 (G4 remainder).

PR #1322 routed the normalized differences (NDVI/NDRE/NDWI/NDMI/NBR/GNDVI)
through ``band_math.normalized_difference``. EVI/SAVI/VARI/GLI/SIPI/ARVI/
RECI/GCI/MSI/CCCI and the soil indices (BSI/NDTI/NDSI/DBSI/SATVI) still divided
by ``where(den == 0, 1e-10, den)``: a Sentinel-2 L2A pixel with BOA offset
−0.1 (negative reflectance) or a near-zero denominator published ±6e7..5e9 and
corrupted the field mean. Each index now has a validity rule (non-negative
finite bands, denominator ≥ MIN_REFLECTANCE_DENOMINATOR, result inside the
documented range); invalid ⇒ NaN ⇒ excluded from stats.
لكلّ مؤشّر: حالة سالبة (نمط التدقيق) + مقام صفريّ + بكسل صالح بقيمة دقيقة.
"""

import band_math
import numpy as np
import pytest
import soil_indices
from test_normalized_difference_validity import _run_process_pixels

pytestmark = pytest.mark.unit

# Pixel columns in every case: [audit-style negative reflectance,
# zero/near-zero denominator, known-valid pixel]. Values are reflectance.
# indicator: (band attrs in file order, per-band pixel values, valid value)
_CASES = {
    "evi": (
        ("blue", "red", "nir"),
        ([0.003, 0.18, 0.05], [-0.003, 0.05, 0.1], [0.0, 0.05, 0.3]),
        2.5 * 0.2 / (0.3 + 0.6 - 0.375 + 1.0),
    ),
    "savi": (
        ("red", "nir"),
        ([0.003, -0.3, 0.1], [-0.003, -0.2, 0.3]),
        1.5 * 0.2 / 0.9,
    ),
    "vari": (
        ("blue", "red", "green"),
        ([0.0, 0.11, 0.03], [-0.003, 0.05, 0.04], [0.003, 0.06, 0.08]),
        0.04 / 0.09,
    ),
    "gli": (
        ("blue", "red", "green"),
        ([-0.003, 0.0, 0.03], [-0.003, 0.0, 0.04], [0.003, 0.0, 0.08]),
        0.09 / 0.23,
    ),
    "sipi": (
        ("blue", "red", "nir"),
        ([0.0, 0.05, 0.03], [-0.003, 0.1, 0.04], [-0.003, 0.1, 0.4]),
        0.37 / 0.36,
    ),
    "arvi": (
        ("blue", "red", "nir"),
        ([-0.003, 0.2, 0.03], [0.0, 0.05, 0.04], [-0.003, 0.1, 0.4]),
        0.35 / 0.45,
    ),
    "reci": (
        ("rededge", "nir"),
        ([-0.001, 0.0, 0.1], [0.3, 0.3, 0.4]),
        3.0,
    ),
    "gci": (
        ("green", "nir"),
        ([-0.001, 0.0, 0.1], [0.3, 0.3, 0.4]),
        3.0,
    ),
    "msi": (
        ("nir", "swir1"),
        ([-0.003, 0.0, 0.4], [0.2, 0.2, 0.1]),
        0.25,
    ),
    "ccci": (
        ("red", "nir", "rededge"),
        ([0.04, 0.1, 0.04], [0.4, 0.1, 0.4], [-0.01, 0.05, 0.1]),
        0.6 / (0.36 / 0.44),
    ),
    # Soil normalized differences: the shared ND kernel keeps the legacy 0/0 → 0
    # contract for all-zero bands, so the "zero denominator" column is the
    # mixed-sign one (A + B == 0), which is what produced ±6e7.
    "ndti": (
        ("swir2", "swir1"),
        ([-0.003, -0.003, 0.1], [0.003, 0.003, 0.3]),
        0.5,
    ),
    "ndsi": (
        ("swir2", "swir1"),
        ([-0.003, -0.003, 0.1], [0.003, 0.003, 0.3]),
        0.5,
    ),
    "bsi": (
        ("blue", "red", "nir", "swir2"),
        (
            [-0.01, 0.0, 0.1],
            [0.2, 0.0, 0.2],
            [0.3, -0.003, 0.3],
            [0.4, 0.003, 0.4],
        ),
        0.2,
    ),
}


def _direct(indicator, bands):
    a = {k: np.asarray(v, dtype="float32") for k, v in bands.items()}
    if indicator in ("reci", "gci"):
        ref = a["rededge"] if indicator == "reci" else a["green"]
        return band_math.chlorophyll_index(a["nir"], ref, np)
    if indicator in ("vari", "gli"):
        return getattr(band_math, indicator)(a["blue"], a["red"], a["green"], np)
    if indicator in ("evi", "sipi", "arvi"):
        return getattr(band_math, indicator)(a["blue"], a["red"], a["nir"], np)
    if indicator == "savi":
        return band_math.savi(a["red"], a["nir"], np)
    if indicator == "msi":
        return band_math.msi(a["nir"], a["swir1"], np)
    if indicator == "ccci":
        return band_math.ccci(a["red"], a["nir"], a["rededge"], np)
    if indicator == "bsi":
        return soil_indices.compute_bsi(a["blue"], a["red"], a["nir"], a["swir2"], np)
    fn = soil_indices.compute_ndti if indicator == "ndti" else soil_indices.compute_ndsi
    return fn(a["swir1"], a["swir2"], np)


@pytest.mark.parametrize("indicator", sorted(_CASES))
def test_negative_and_zero_denominator_pixels_are_nodata_valid_pixel_exact(indicator):
    attrs, values, expected = _CASES[indicator]
    out = _direct(indicator, dict(zip(attrs, values, strict=True)))
    assert np.isnan(out[0]), f"{indicator}: negative reflectance must be NoData, got {out[0]}"
    assert np.isnan(out[1]), f"{indicator}: zero denominator must be NoData, got {out[1]}"
    assert out[2] == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize("indicator", sorted(_CASES))
def test_runtime_invalid_pixels_do_not_corrupt_published_stats(tmp_path, indicator):
    attrs, values, expected = _CASES[indicator]
    stats = _run_process_pixels(tmp_path, indicator, attrs, *values)
    assert stats["valid_pixels"] == 1
    assert stats["mean"] == pytest.approx(expected, rel=1e-6)
    assert stats["min"] == stats["max"]


@pytest.mark.parametrize(
    "fn,lo,hi",
    [
        (lambda b, r, n: band_math.evi(b, r, n, np), -1.0, 1.0),
        (lambda b, r, n: band_math.savi(r, n, np), -1.5, 1.5),
        (lambda b, r, n: band_math.vari(b, r, n, np), -1.0, 1.0),
        (lambda b, r, n: band_math.gli(b, r, n, np), -1.0, 1.0),
        (lambda b, r, n: band_math.sipi(b, r, n, np), 0.0, 2.0),
        (lambda b, r, n: band_math.arvi(b, r, n, np), -1.0, 1.0),
        (lambda b, r, n: band_math.chlorophyll_index(n, r, np), -1.0, np.inf),
        (lambda b, r, n: band_math.msi(n, b, np), 0.0, np.inf),
        (lambda b, r, n: band_math.ccci(r, n, b, np), 0.0, 1.0),
        (lambda b, r, n: soil_indices.compute_bsi(b, r, n, b, np), -1.0, 1.0),
        (lambda b, r, n: soil_indices.compute_ndti(n, r, np), -1.0, 1.0),
        (lambda b, r, n: soil_indices.compute_ndsi(n, r, np), -1.0, 1.0),
    ],
)
def test_random_l2a_like_reflectance_stays_in_documented_range(fn, lo, hi):
    # L2A-like inputs incl. the −0.1 BOA offset floor: no finite output may leave
    # the documented range, and nothing may reach the old ±1e7 epsilon scale.
    rng = np.random.default_rng(1322)
    b, r, n = (rng.uniform(-0.1, 1.2, 20000).astype("float32") for _ in range(3))
    out = fn(b, r, n)
    finite = out[np.isfinite(out)]
    assert finite.size > 1000
    assert (finite >= lo).all() and (finite <= hi).all()
    assert np.isnan(out[n < 0]).all()  # every index above reads ``n``


def test_bsi_masks_a_negative_band_hidden_inside_a_nonnegative_sum():
    # (SWIR2 + RED) = 0.39 ≥ 0 hides RED = −0.01; the band itself is invalid.
    out = soil_indices.compute_bsi(
        np.array([0.1]), np.array([-0.01]), np.array([0.3]), np.array([0.4]), np
    )
    assert np.isnan(out[0])


def test_dbsi_and_satvi_mask_negative_reflectance_and_keep_valid_values():
    dbsi = soil_indices.compute_dbsi(
        np.array([0.1, 0.1]), np.array([0.3, -0.003]), np.array([0.2, 0.2]), np
    )
    assert dbsi[0] == pytest.approx(0.5 - 0.2)
    assert np.isnan(dbsi[1])
    satvi = soil_indices.compute_satvi(
        np.array([0.1, -0.1]), np.array([0.3, 0.3]), np.array([0.2, 0.2]), np
    )
    assert satvi[0] == pytest.approx((0.2 / 0.9) * 1.5 - 0.1)
    assert np.isnan(satvi[1])


def test_soil_nd_indices_keep_the_shared_kernel_all_zero_contract():
    # Same contract as band_math.normalized_difference: 0/0 with valid (non-negative)
    # bands → 0, not NaN; the mixed-sign A + B == 0 case is what is masked.
    z = np.array([0.0])
    assert soil_indices.compute_ndti(z, z, np)[0] == 0.0
    assert soil_indices.compute_ndsi(z, z, np)[0] == 0.0
    assert soil_indices.compute_bsi(z, z, z, z, np)[0] == 0.0


def test_guarded_quotient_refuses_a_missing_band():
    with pytest.raises(ValueError, match="missing band"):
        band_math.sipi(None, np.array([0.1]), np.array([0.4]), np)
