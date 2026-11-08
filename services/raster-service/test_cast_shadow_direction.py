"""Cast-shadow direction: a barrier must shade the side facing away from the sun.

Regression for the reversed blocker sampling (each pixel sampled the cell on
the far side from the sun, so the sunlit side of a barrier was flagged).
"""

import numpy as np
import pytest
import raster_topographic_qa as tq

pytestmark = pytest.mark.unit

N = 9
MID = N // 2


def _mask(dem, azimuth):
    out = tq.compute_cast_shadow_mask_from_dem(
        dem,
        pixel_size_m=10.0,
        sun_azimuth_deg=azimuth,
        sun_altitude_deg=30.0,
        max_steps=16,
    )
    assert out["cast_shadow_available"] is True
    assert out["cast_shadow_algorithm_version"] == tq.CAST_SHADOW_ALGORITHM_VERSION
    return out["mask"]


def test_audit_case_north_sun_shades_rows_south_of_barrier():
    dem = np.zeros((N, N), dtype="float32")
    dem[1, :] = 100.0
    mask = _mask(dem, 0.0)
    # Row 0 lies between the barrier and the (northern) sun: never shaded.
    assert not mask[0].any()
    assert not mask[1].any()  # barrier crest itself
    # Rows just south of the barrier are shaded across the full width.
    assert mask[2].all()
    assert mask[3].all()


@pytest.mark.parametrize(
    ("azimuth", "barrier", "shaded", "sunlit"),
    [
        # sun in the north -> shadow falls south (larger row index)
        (0.0, (slice(MID, MID + 1), slice(None)), (MID + 1, slice(None)), (MID - 1, slice(None))),
        # sun in the east -> shadow falls west (smaller col index)
        (90.0, (slice(None), slice(MID, MID + 1)), (slice(None), MID - 1), (slice(None), MID + 1)),
        # sun in the south -> shadow falls north (smaller row index)
        (180.0, (slice(MID, MID + 1), slice(None)), (MID - 1, slice(None)), (MID + 1, slice(None))),
        # sun in the west -> shadow falls east (larger col index)
        (270.0, (slice(None), slice(MID, MID + 1)), (slice(None), MID + 1), (slice(None), MID - 1)),
    ],
)
def test_shadow_falls_on_the_side_opposite_the_sun(azimuth, barrier, shaded, sunlit):
    dem = np.zeros((N, N), dtype="float32")
    dem[barrier] = 100.0
    mask = _mask(dem, azimuth)
    assert mask[shaded].all(), f"azimuth {azimuth}: lee side must be shaded"
    assert not mask[sunlit].any(), f"azimuth {azimuth}: sun-facing side must be lit"


def test_low_barrier_below_solar_line_casts_no_shadow():
    dem = np.zeros((N, N), dtype="float32")
    dem[MID, :] = 1.0  # 1 m rise vs 10 m * tan(30 deg) ~= 5.8 m solar line
    assert not _mask(dem, 0.0).any()


def test_envelope_records_cast_shadow_algorithm_version():
    dem = np.zeros((N, N), dtype="float32")
    dem[MID, :] = 100.0
    out = tq.build_topographic_qa_from_dem_array(
        dem, pixel_size_m=10.0, sun_azimuth_deg=0.0, sun_altitude_deg=30.0
    )
    assert out["cast_shadow_algorithm_version"] == "sahool.cast_shadow_raymarch/2"
    no_sun = tq.build_topographic_qa_from_dem_array(dem, pixel_size_m=10.0)
    assert no_sun["cast_shadow_algorithm_version"] is None
