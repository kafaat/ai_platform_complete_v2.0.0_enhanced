"""The optical processor only publishes products for which it has the inputs."""

import numpy as np
import pytest
import raster_processing_runtime
import rasterio
from raster_api_models import BandMapping, ProcessRequest
from raster_settings import LANDSAT_UNIQUE_INDICES
from rasterio.transform import from_origin


@pytest.fixture
def optical_scene(tmp_path):
    path = tmp_path / "optical.tif"
    values = np.full((3, 16, 16), 0.2, dtype="float32")
    values[1] = 0.6
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        count=3,
        height=16,
        width=16,
        dtype="float32",
        crs="EPSG:32638",
        transform=from_origin(400000, 1770000, 10, 10),
    ) as dataset:
        dataset.write(values)
    return path


def compute(path, index, bands):
    request = ProcessRequest(
        tenant_id="test",
        raster_url=path.as_uri(),
        indicator=index,
        source_format="custom",
        bands=BandMapping(**bands),
        apply_cloud_mask=False,
    )
    return raster_processing_runtime.process_pixels(request, "product", upload_dir=str(path.parent))


@pytest.mark.parametrize("index", sorted(LANDSAT_UNIQUE_INDICES))
def test_thermal_request_on_raw_optical_never_writes_a_product(optical_scene, index):
    with pytest.raises(ValueError, match=f"unsupported_raw_optical_indicator: {index}"):
        compute(optical_scene, index, {"red": 1, "nir": 2})
    assert list(optical_scene.parent.glob("*.tif")) == [optical_scene]


def test_fapar_has_its_own_computation(optical_scene):
    stats, _, _, product = compute(optical_scene, "fapar", {"red": 1, "nir": 2})
    assert product["cog_url"]
    assert stats["mean"] == pytest.approx(1.24 * 0.5 - 0.168, abs=1e-5)


@pytest.mark.parametrize("missing", ["red", "green", "blue"])
def test_raw_truecolor_requires_all_three_channels(optical_scene, missing):
    bands = {"red": 1, "green": 2, "blue": 3}
    del bands[missing]
    with pytest.raises(ValueError, match="truecolor_requires_rgb"):
        compute(optical_scene, "truecolor", bands)
    assert list(optical_scene.parent.glob("*.tif")) == [optical_scene]
