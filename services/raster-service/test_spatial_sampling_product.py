"""Product spacing, sensor provenance and exported COG must agree across restart."""

import json
from pathlib import Path

import pytest
from rasterio import open as open_raster
from rasterio.transform import from_origin
from test_raster_pixel_geometry import _process


@pytest.mark.unit
def test_rectangular_cog_does_not_claim_native_sensor_resolution(tmp_path):
    _, _, legacy_spacing, meta = _process(
        tmp_path, crs="EPSG:32638", transform=from_origin(400000, 1772000, 5, 12), clip=None
    )
    assert legacy_spacing == 5
    expected = {
        "output_pixel_size_m": [5, 12],
        "native_band_resolution_m": None,
        "resampling_method": None,
    }
    assert meta["spatial_sampling"] == expected
    with open_raster(Path(meta["cog_url"].removeprefix("file://"))) as dataset:
        assert json.loads(dataset.tags()["SAHOOL_SPATIAL_SAMPLING"]) == expected


@pytest.mark.unit
def test_untrusted_process_json_cannot_assign_native_sensor_origin():
    from raster_api_models import ProcessRequest

    req = ProcessRequest.model_validate(
        {
            "tenant_id": "t",
            "indicator": "ndvi",
            "source_format": "custom",
            "bands": {"red": 1, "nir": 2},
            "_spatial_sampling": {"native_band_resolution_m": {"B04": 1}},
        }
    )
    assert req._spatial_sampling is None


@pytest.mark.unit
def test_field_polygon_hash_and_sampling_are_independent_provenance_inputs():
    from raster_provenance import build_provenance

    polygon = {"type": "Polygon", "coordinates": [[[44, 16], [45, 16], [45, 17], [44, 16]]]}
    old = build_provenance("ndre", clip_polygon=polygon)
    new = build_provenance(
        "ndre", clip_polygon=polygon, spatial_sampling={"output_pixel_size_m": [20, 20]}
    )
    assert old["clip_polygon_hash"] == new["clip_polygon_hash"]
    assert old["provenance_hash"] != new["provenance_hash"]
