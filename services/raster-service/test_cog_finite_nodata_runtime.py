"""Exercise on-disk nodata and masks without depending on writer variable names."""

import cog_writer
import numpy as np
import pytest
import rasterio
from rasterio.enums import MaskFlags
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit


class WindowOnlyArray:
    """Reject whole-image conversion and reads wider than a writer tile."""

    def __init__(self, data):
        self.data = data
        self.shape = data.shape
        self.reads = []

    def __array__(self, *args, **kwargs):
        raise AssertionError("whole-image conversion")

    def __getitem__(self, key):
        rows, cols = key
        assert isinstance(rows, slice) and isinstance(cols, slice)
        assert 0 < rows.stop - rows.start <= 512
        assert 0 < cols.stop - cols.start <= 512
        self.reads.append((rows.start, rows.stop, cols.start, cols.stop))
        return self.data[key]


@pytest.mark.parametrize("nodata", [-9999.0, -32768.0, np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("mode", ["mixed", "all_invalid", "all_valid"])
def test_windowed_cog_finite_nodata_and_internal_masks(tmp_path, nodata, mode):
    sentinel = nodata if np.isfinite(nodata) else -9999.0
    # Uneven edge tiles; invalid samples straddle both 512-pixel boundaries.
    data = np.ma.array(np.full((517, 523), 0.25, dtype="float64"), mask=False)
    if mode == "mixed":
        for row in (0, 511, 512, 516):
            data.data[row, 509:515] = [np.nan, np.inf, -np.inf, sentinel, 0, -0.5]
            data.mask[row, 515] = True  # finite masked sample must stay invalid
        data.data[513, 516] = np.finfo("float64").max  # overflows float32
    elif mode == "all_invalid":
        data.mask[:] = True
    original = data.copy()
    with np.errstate(over="ignore"):
        converted = data.data.astype("float32")
    expected_valid = ~data.mask & np.isfinite(converted) & (converted != sentinel)
    source = WindowOnlyArray(data)
    output = tmp_path / "result.tif"
    transform = from_origin(44, 16, 0.0001, 0.0001)
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False), np.errstate(over="ignore"):
        result = cog_writer.write_cog(
            source, str(output), transform, crs="EPSG:4326", nodata=nodata
        )
    assert result["written"] and result["validation"]["valid"]
    assert source.reads == [
        (0, 512, 0, 512),
        (0, 512, 512, 523),
        (512, 517, 0, 512),
        (512, 517, 512, 523),
    ]
    assert list(tmp_path.iterdir()) == [output]  # no external mask or staging artifacts
    with rasterio.open(output) as src:
        assert src.nodata == sentinel and np.isfinite(src.nodata)
        assert src.transform == transform and src.crs.to_epsg() == 4326
        assert MaskFlags.per_dataset in src.mask_flag_enums[0]
        stored = src.read(1)
        assert np.isfinite(stored).all()
        np.testing.assert_array_equal(src.read_masks(1), expected_valid.astype("uint8") * 255)
        np.testing.assert_array_equal(src.read(1, masked=True).mask, ~expected_valid)
        np.testing.assert_array_equal(stored[~expected_valid], sentinel)
        np.testing.assert_array_equal(stored[expected_valid], converted[expected_valid])
    np.testing.assert_array_equal(data.data, original.data)
    np.testing.assert_array_equal(data.mask, original.mask)


@pytest.mark.parametrize("shape", [(17, 19), (512, 512), (513, 1), (1, 513)])
def test_windows_cover_each_pixel_once_including_thin_edges(shape):
    coverage = np.zeros(shape, dtype="uint8")
    for window in cog_writer.write_windows(*shape):
        assert 0 < window.width <= 512 and 0 < window.height <= 512
        coverage[window.toslices()] += 1
    assert np.all(coverage == 1)
