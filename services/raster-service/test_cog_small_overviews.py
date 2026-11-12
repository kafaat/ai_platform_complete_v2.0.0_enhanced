"""Small field clips retain masks and sampling metadata through COG finalization."""

import json

import cog_writer
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("shape,levels", [((4, 4), [2, 4]), ((1, 1), []), ((2, 8), [2, 4, 8])])
@pytest.mark.parametrize("writer", ["indicator", "rgba", "open_rgba"])
def test_tiny_field_clip_round_trip(tmp_path, shape, levels, writer):
    transform = from_origin(500000, 1800000, 20, 20)
    path = str(tmp_path / "tiny.tif")
    sampling = {"output_pixel_size_m": 20}
    if writer == "indicator":
        data = np.ma.array(np.ones(shape, dtype="float32"), mask=False)
        if shape != (1, 1):
            data.mask[0, 0] = True
        result = cog_writer.write_cog(
            data, path, transform, "EPSG:32638", spatial_sampling=sampling
        )
    else:
        rgba = np.full((4, *shape), 127, dtype="uint8")
        if shape != (1, 1):
            rgba[3, 0, 0] = 0
        if writer == "rgba":
            result = cog_writer.write_rgba_cog(
                rgba, path, transform, "EPSG:32638", spatial_sampling=sampling
            )
        else:
            with rasterio.open(
                tmp_path / "source.tif",
                "w",
                driver="GTiff",
                width=shape[1],
                height=shape[0],
                transform=transform,
                crs="EPSG:32638",
                count=4,
                dtype="uint8",
            ) as source:
                source.write(rgba)
            with rasterio.open(tmp_path / "source.tif") as source:
                result = cog_writer.write_rgba_cog_source(source, path, spatial_sampling=sampling)
    assert result["validation"]["valid"], result
    with rasterio.open(path) as ds:
        assert ds.shape == shape
        assert ds.overviews(1) == levels
        assert result["overviews"] == levels
        assert json.loads(ds.tags()["SAHOOL_SPATIAL_SAMPLING"]) == sampling
        assert np.count_nonzero(ds.dataset_mask()) == np.prod(shape) - int(shape != (1, 1))
