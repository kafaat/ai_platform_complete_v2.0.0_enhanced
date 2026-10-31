"""Offline source/metadata witnesses for STAC CRS provenance."""

import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stac_search
import stac_vrt


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "red.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="uint16",
        crs="EPSG:32638",
        transform=from_origin(400000, 1772000, 10, 10),
    ) as dst:
        dst.write(np.full((2, 2), 2000, dtype="uint16"), 1)
    item = {
        "id": "test",
        "collection": "sentinel-2-c1-l2a",
        "properties": {},
        "assets": {
            "red": {
                "href": str(path),
                "eo:bands": [{"common_name": "red"}],
                "raster:bands": [{"scale": 0.0001, "offset": 0.0}],
            }
        },
    }
    return path, item


@pytest.mark.parametrize("location", ["item", "asset"])
@pytest.mark.parametrize(
    "key,value",
    [
        ("proj:epsg", 32639),
        ("proj:code", "EPSG:32639"),
        ("proj:wkt2", rasterio.crs.CRS.from_epsg(32639).to_wkt()),
        ("proj:epsg", True),
        ("proj:code", "not-a-crs"),
        ("proj:projjson", {}),
    ],
)
def test_conflicting_or_invalid_projection_rejected(source, tmp_path, location, key, value):
    path, item = source
    target = item["properties"] if location == "item" else item["assets"]["red"]
    target[key] = value
    # Exercise the real production context copy before the real VRT constructor.
    context = stac_search.radiometry_context_from_item(item)
    with pytest.raises(ValueError, match="STAC.*(CRS|declaration)"):
        stac_vrt.build_band_vrt({"red": str(path)}, str(tmp_path), stac_item=context)
    assert not list(tmp_path.glob("stac_stack_*"))


def test_matching_asset_override_preserves_pixels(source, tmp_path):
    path, item = source
    item["properties"]["proj:epsg"] = 32639
    item["assets"]["red"].update({"proj:epsg": 32638, "proj:code": "EPSG:32638"})
    context = stac_search.radiometry_context_from_item(item)
    vrt, _ = stac_vrt.build_band_vrt({"red": str(path)}, str(tmp_path), stac_item=context)
    with rasterio.open(vrt) as src:
        assert src.crs == rasterio.crs.CRS.from_epsg(32638)
        np.testing.assert_array_equal(src.read(1), np.full((2, 2), 2000))


def test_conflicting_second_declaration_not_ignored(source, tmp_path):
    path, item = source
    item["assets"]["red"].update({"proj:epsg": 32638, "proj:code": "EPSG:32639"})
    with pytest.raises(ValueError, match="conflicts with TIFF CRS"):
        stac_vrt.build_band_vrt({"red": str(path)}, str(tmp_path), stac_item=item)


def test_projection_context_is_deep_copied(source):
    _, item = source
    item["assets"]["red"]["proj:projjson"] = {"type": "ProjectedCRS"}
    context = stac_search.radiometry_context_from_item(item)
    item["assets"]["red"]["proj:projjson"]["type"] = "mutated"
    assert context["assets"]["red"]["proj:projjson"]["type"] == "ProjectedCRS"


def test_later_asset_conflict_removes_already_created_sidecars(source, tmp_path):
    import copy
    import shutil

    path, item = source
    nir = tmp_path / "nir.tif"
    shutil.copyfile(path, nir)
    item["assets"]["nir"] = copy.deepcopy(item["assets"]["red"])
    item["assets"]["nir"].update({"href": str(nir), "proj:epsg": 32639})
    with pytest.raises(ValueError, match="conflicts with TIFF CRS"):
        stac_vrt.build_band_vrt({"red": str(path), "nir": str(nir)}, str(tmp_path), stac_item=item)
    assert not list(tmp_path.glob("stac_stack_*"))


@pytest.mark.parametrize(
    "item_key,asset_key", [("proj:epsg", "proj:code"), ("proj:code", "proj:epsg")]
)
def test_asset_authority_overrides_legacy_alias(source, tmp_path, item_key, asset_key):
    path, item = source
    item["properties"][item_key] = 32639 if item_key == "proj:epsg" else "EPSG:32639"
    item["assets"]["red"][asset_key] = 32638 if asset_key == "proj:epsg" else "EPSG:32638"
    stac_vrt.build_band_vrt({"red": str(path)}, str(tmp_path), stac_item=item)


def test_truthful_source_crs_is_reprojected_to_target_grid(source, tmp_path):
    import copy

    from rasterio.warp import transform_bounds

    path, item = source
    nir = tmp_path / "nir.tif"
    with rasterio.open(path) as src:
        left, bottom, right, top = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    with rasterio.open(
        nir,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(left, top, (right - left) / 2, (top - bottom) / 2),
    ) as dst:
        dst.write(np.full((2, 2), 6000, dtype="uint16"), 1)
    item["properties"]["proj:code"] = "EPSG:32638"
    item["assets"]["nir"] = copy.deepcopy(item["assets"]["red"])
    item["assets"]["nir"].update({"href": str(nir), "proj:code": "EPSG:4326"})
    vrt, bands = stac_vrt.build_band_vrt(
        {"red": str(path), "nir": str(nir)}, str(tmp_path), stac_item=item
    )
    with rasterio.open(vrt) as src:
        assert src.crs == rasterio.crs.CRS.from_epsg(32638)
        np.testing.assert_array_equal(src.read(bands["nir"]), np.full((2, 2), 6000))
