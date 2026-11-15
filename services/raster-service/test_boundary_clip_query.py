import numpy as np
import pytest
import rasterio
from fastapi import HTTPException
from raster_cdse_tile_runtime import parse_poly
from rasterio.transform import from_origin
from routers import soil_tiles, terrain_tiles
from tile_render import apply_polygon_mask, mask_array_by_polygon

OUTER = "40,10;44,10;44,14;40,14;40,10"
HOLE = "41,11;42,11;42,12;41,12;41,11"
ISLAND = "47,10;48,10;48,11;47,11;47,10"
WIRE = OUTER + "|" + HOLE + "!" + ISLAND


def test_masks_same_pixels_on_live_cog_soil_and_contours(tmp_path):
    transform = from_origin(40, 14, 1, 1)
    arr = np.ones((4, 8), dtype="float32")
    path = tmp_path / "synthetic.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=8,
        height=4,
        count=1,
        dtype="float32",
        transform=transform,
        crs="EPSG:4326",
    ) as dst:
        dst.write(arr, 1)
    geom = parse_poly(WIRE)
    assert geom["type"] == "MultiPolygon"
    assert [len(part) for part in geom["coordinates"]] == [2, 1]
    assert apply_polygon_mask(str(path), geom) == 16
    with rasterio.open(path) as src:
        mask = np.isfinite(src.read(1))
    expected = np.zeros((4, 8), dtype=bool)
    expected[:, :4] = True
    expected[2, 1] = False
    expected[3, 7] = True
    np.testing.assert_array_equal(mask, expected)
    for reader in [soil_tiles._parse_poly_points, terrain_tiles._parse_poly_points]:
        masked = mask_array_by_polygon(arr, transform, None, reader(WIRE))
        np.testing.assert_array_equal(np.isfinite(masked), expected)


def test_legacy_ring_is_closed_and_hole_stays_a_hole():
    assert parse_poly("40,10;44,10;40,14")["coordinates"][0][-1] == [40, 10]
    poly = parse_poly(OUTER + "|" + HOLE)
    assert poly["type"] == "Polygon" and len(poly["coordinates"]) == 2


@pytest.mark.parametrize("value", [OUTER + "|", OUTER + "!", "nan,0;1,1;2,2"])
def test_malformed_explicit_clip_is_rejected_instead_of_rendering_unmasked(value):
    with pytest.raises(HTTPException) as error:
        parse_poly(value)
    assert error.value.status_code == 422
