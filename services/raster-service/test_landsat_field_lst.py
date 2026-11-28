"""Regression for #1637: actual GeoTIFF samples, UTM geometry, holes and COG I/O."""

import asyncio
import hashlib
from pathlib import Path

import db_persist
import numpy as np
import pytest
import raster_api_models as models
import raster_processing_runtime as runtime
import rasterio
import stac_search
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from shapely.geometry import Polygon, box, mapping

TENANT = "ce76dba6-2f31-44bd-afbd-3c2169c433d5"
OTHER = "db07980d-e9d7-4fc4-b721-d55f1ddfc15c"
CRS = "EPSG:32638"
GRID = from_origin(500000, 1700000, 30, 30)
SCENE = "LC09_L2SP_fixture"
EXPECTED = 44947 * 0.00341802 + 149
URL = "https://fixture.example/"


def field_polygon():
    def ring(left, bottom, right, top):
        return [GRID * p for p in box(left, bottom, right, top).exterior.coords]

    poly = Polygon(ring(1.05, 1.05, 3.95, 3.95), [ring(2.05, 2.05, 2.95, 2.95)])
    return transform_geom(CRS, "EPSG:4326", mapping(poly))


def write_raster(path, arr, nodata, *, unit=None, transform=GRID, scale=1, offset=0):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=arr.shape[1],
        height=arr.shape[0],
        count=1,
        dtype=arr.dtype,
        nodata=nodata,
        crs=CRS,
        transform=transform,
    ) as dst:
        dst.write(arr, 1)
        dst.scales, dst.offsets = [scale], [offset]
        if unit:
            dst.set_band_unit(1, unit)


def make_case(tmp_path, monkeypatch, calibrated=False):
    arr = np.full((5, 5), 58000, dtype="uint16")
    arr[1:4, 1:4] = 0
    arr[1, 1], arr[2, 2], arr[3, 3] = 44947, 62000, 55000
    dtype, scale, offset, fill = "uint16", 0.00341802, 149, 0
    if calibrated:
        dtype, scale, offset, fill = "float32", 1, 0, -9999
        arr = np.where(arr, arr.astype("float64") * 0.00341802 + 149, fill).astype(dtype)
    write_raster(tmp_path / "st.tif", arr, fill, unit="K" if calibrated else None)
    qa = np.full((5, 5), 64, dtype="uint16")
    qa[3, 3] = 8  # one cloudy interior pixel
    write_raster(tmp_path / "qa.tif", qa, 1)

    def asset(name, band):
        path = tmp_path / name
        return {
            "href": URL + name,
            "raster:bands": [band],
            "file:checksum": "1220" + hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    feat = {
        "id": SCENE,
        "collection": "landsat-c2-l2",
        "properties": {"datetime": "2026-11-13T07:00:00Z", "landsat:correction": "L2SP"},
        "assets": {
            "lwir11": {
                **asset(
                    "st.tif",
                    {
                        "unit": "kelvin",
                        "scale": scale,
                        "offset": offset,
                        "data_type": dtype,
                        "nodata": fill,
                        "spatial_resolution": 30,
                    },
                ),
                "roles": ["data", "temperature"],
                "gsd": 100,
            },
            "qa_pixel": asset("qa.tif", {"data_type": "uint16", "nodata": 1}),
        },
    }
    scene = stac_search.landsat_unique_payload(feat)
    req = models.ProcessRequest(
        tenant_id=TENANT,
        field_id="fld_a",
        raster_url=scene["thermal_urls"]["lst"],
        source_format="landsat8",
        indicator="lst",
        bands={},
        precomputed_index=True,
        provider=scene["provider"],
        scene_id=scene["item_id"],
        capture_datetime=scene["datetime"],
        clip_polygon_geojson=field_polygon(),
        geometry_revision=4,
        apply_cloud_mask=True,
    )
    req._landsat_st = scene.get("thermal_contract")
    ctx = runtime.make_processing_context(upload_dir=str(tmp_path))
    ctx._safe_raster_source = lambda url: str(tmp_path / url.rsplit("/", 1)[-1])

    async def saved(field_id, tenant_id):
        if (field_id, tenant_id) == ("fld_a", TENANT):
            return {"geometry": field_polygon(), "revision": 4}
        return None

    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", saved)
    return ctx, req, feat


@pytest.mark.parametrize("calibrated", [False, True], ids=["DN", "kelvin"])
def test_known_pixel(tmp_path, monkeypatch, calibrated):
    ctx, req, _ = make_case(tmp_path, monkeypatch, calibrated)
    stats, bounds, res, meta = ctx._process_precomputed_pixels(req, "layer")
    print("PIXELS", stats["mean"], stats["valid_pixels"], stats.get("median"), bounds, res)
    assert stats["mean"] == pytest.approx(EXPECTED, abs=2e-5)
    assert stats["median"] == pytest.approx(EXPECTED, abs=2e-5)
    assert stats["valid_pixels"] == 1 and stats["nodata_pixels"] == 7
    assert stats["thermal"]["valid_area_m2"] == 900
    assert stats["thermal"]["qa_mask_version"]
    assert meta["spatial_sampling"]["native_band_resolution_m"] == {"lwir11": 100}
    assert res == 30 and len(bounds) == 4
    assert stats["cog"]["validation"]["valid"]
    with rasterio.open(stats["cog"]["path"]) as src:
        assert src.shape == (3, 3) and src.crs.to_string() == CRS
        assert src.transform == from_origin(500030, 1699970, 30, 30)
        assert src.units == ("K",) and src.scales == (1,) and src.offsets == (0,)
        actual = src.read(1, masked=True)
        assert actual.count() == 1 and actual[0, 0] == pytest.approx(EXPECTED, abs=2e-5)
        assert actual.mask[1, 1] and actual.mask[2, 2]


def assert_refused(tmp_path, ctx, req, reason):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        ctx._process_precomputed_pixels(req, "refused")
    detail = error.value.detail
    assert (detail["code"] if isinstance(detail, dict) else detail) == reason
    assert not list(tmp_path.glob("lst_*.tif"))


@pytest.mark.parametrize(
    "key,value,code",
    [
        ("unit", None, "band_metadata_conflict"),
        ("unit", "celsius", "band_metadata_conflict"),
        ("scale", None, "ambiguous_encoding"),
        ("offset", 150, "ambiguous_encoding"),
        ("data_type", "float32", "band_metadata_conflict"),
        ("nodata", 1, "band_metadata_conflict"),
    ],
)
def test_band_contract(tmp_path, monkeypatch, key, value, code):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    req._landsat_st["band"][key] = value
    assert_refused(tmp_path, ctx, req, "landsat_lst_" + code)


@pytest.mark.parametrize(
    "attr,value,code",
    [
        ("scene_id", "other", "catalogue_contract_required"),
        ("raster_url", URL + "other", "catalogue_contract_required"),
        ("field_id", "fld_b", "field_unavailable"),
        ("tenant_id", OTHER, "field_unavailable"),
        ("geometry_revision", 2, "field_revision_changed"),
        ("clip_polygon_geojson", None, "invalid_field_geometry"),
        (
            "clip_polygon_geojson",
            {"type": "Point", "coordinates": [45, 15]},
            "invalid_field_geometry",
        ),
        (
            "clip_polygon_geojson",
            {
                "type": "Polygon",
                "coordinates": [[[45, 15], [46, 16], [46, 15], [45, 16], [45, 15]]],
            },
            "invalid_field_geometry",
        ),
        ("clip_polygon_geojson", mapping(box(44, 15, 46, 16)), "clip_outside_field"),
    ],
)
def test_request_binding(tmp_path, monkeypatch, attr, value, code):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    setattr(req, attr, value)
    assert_refused(tmp_path, ctx, req, "landsat_lst_" + code)


def test_public_request_cannot_supply_receipt(tmp_path, monkeypatch):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    external = models.ProcessRequest.model_validate(
        req.model_dump() | {"_landsat_st": req._landsat_st}
    )
    assert_refused(tmp_path, ctx, external, "landsat_lst_catalogue_contract_required")


def test_discovery_requires_one_surface_temperature_band(tmp_path, monkeypatch):
    ctx, req, feat = make_case(tmp_path, monkeypatch)
    feat["collection"] = "landsat-c2-l1"
    req._landsat_st = stac_search.landsat_unique_payload(feat)["thermal_contract"]
    assert_refused(tmp_path, ctx, req, "landsat_lst_catalogue_contract_required")
    assets = feat["assets"]
    assets["st_b10"] = assets["lwir11"]
    assert stac_search.landsat_unique_payload(feat) is None
    del assets["st_b10"]
    assets["st_qa"] = dict(assets.pop("lwir11"), title="Surface Temperature Quality")
    assert stac_search.landsat_unique_payload(feat) is None


def test_checksum_and_gdal_scale_conflicts(tmp_path, monkeypatch):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    req._landsat_st["checksum"] = "1220" + "0" * 64
    assert_refused(tmp_path, ctx, req, "landsat_lst_asset_integrity_mismatch")
    with rasterio.open(tmp_path / "st.tif", "r+") as ds:
        ds.scales = [0.1]
    assert_refused(tmp_path, ctx, req, "landsat_lst_tiff_metadata_conflict")


def test_qa_required_on_matching_grid(tmp_path, monkeypatch):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    with rasterio.open(tmp_path / "qa.tif", "r+") as ds:
        ds.transform = from_origin(500001, 1700000, 30, 30)
    assert_refused(tmp_path, ctx, req, "landsat_lst_qa_grid_mismatch")
    req._landsat_st["qa"] = None
    assert_refused(tmp_path, ctx, req, "landsat_lst_qa_pixel_missing")


def test_empty_and_oversized_windows(tmp_path, monkeypatch):
    import raster_settings

    ctx, req, _ = make_case(tmp_path, monkeypatch)
    with rasterio.open(tmp_path / "st.tif", "r+") as ds:
        ds.write(np.zeros(ds.shape, dtype="uint16"), 1)
    req._landsat_st["checksum"] = None
    assert_refused(tmp_path, ctx, req, "raw_raster_no_valid_pixels")
    monkeypatch.setattr(raster_settings, "RASTER_MAX_READ_BAND_PIXELS", 8)
    assert_refused(tmp_path, ctx, req, "landsat_lst_window_too_large")


def test_nonoverlapping_field(tmp_path, monkeypatch):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    req.clip_polygon_geojson = mapping(box(44, 15, 44.1, 15.1))
    with rasterio.open(tmp_path / "st.tif") as src:
        footprint = rasterio.warp.transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    assert not box(*footprint).intersects(box(44, 15, 44.1, 15.1))

    async def stored(*_):
        return {"geometry": req.clip_polygon_geojson, "revision": 4}

    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", stored)
    assert_refused(tmp_path, ctx, req, "landsat_lst_field_outside_scene")


def test_source_cog_reingested_as_kelvin(tmp_path, monkeypatch):
    ctx, req, feat = make_case(tmp_path, monkeypatch)
    first, *_ = ctx._process_precomputed_pixels(req, "original")
    path = Path(first["cog"]["path"])
    asset = feat["assets"]["lwir11"]
    asset.update(
        href=URL + path.name,
        **{"file:checksum": "1220" + hashlib.sha256(path.read_bytes()).hexdigest()},
    )
    asset["raster:bands"][0].update(
        data_type="float32", scale=1, offset=0, nodata=ctx.RASTER_NODATA
    )
    req._landsat_st = stac_search.landsat_unique_payload(feat)["thermal_contract"]
    req.raster_url = asset["href"]
    req.apply_cloud_mask = False  # input COG already contains the original per-pixel validity mask
    again, *_ = ctx._process_precomputed_pixels(req, "derived")
    assert again["thermal"]["encoding"] == "kelvin"
    assert again["valid_pixels"] == 1 and again["mean"] == first["mean"]


def test_raw_geotiff_scale_and_stac_scale_applied_once(tmp_path, monkeypatch):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    with rasterio.open(tmp_path / "st.tif", "r+") as ds:
        ds.scales, ds.offsets = [0.00341802], [149.0]
    req._landsat_st["checksum"] = None
    for _ in range(2):
        stats, *_ = ctx._process_precomputed_pixels(req, "repeat")
        assert stats["mean"] == pytest.approx(EXPECTED, abs=2e-5)
        assert stats["thermal"]["asset_integrity"][0]["verdict"] == "no_checksum"


def test_tenant_b_sees_only_its_field(tmp_path, monkeypatch):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    west_field = transform_geom(CRS, "EPSG:4326", mapping(box(500001, 1699851, 500029, 1699999)))
    req.tenant_id, req.field_id, req.clip_polygon_geojson = OTHER, "fld_b", west_field

    async def stored(field, tenant):
        if (field, tenant) == ("fld_b", OTHER):
            return {"geometry": west_field, "revision": 4}
        return None

    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", stored)
    stats, *_ = ctx._process_precomputed_pixels(req, "B")
    assert stats["valid_pixels"] == 5
    assert stats["mean"] == pytest.approx(58000 * 0.00341802 + 149)
    req.clip_polygon_geojson = field_polygon()
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refused:
        ctx._process_precomputed_pixels(req, "foreign")
    assert refused.value.status_code == 403


def test_qa_not_requested_and_raw_range(tmp_path, monkeypatch):
    ctx, req, _ = make_case(tmp_path, monkeypatch)
    with rasterio.open(tmp_path / "st.tif", "r+") as ds:
        arr = ds.read(1)
        arr[1, 2] = 292  # non-fill, below USGS valid range
        ds.write(arr, 1)
    req._landsat_st["checksum"] = None
    req.apply_cloud_mask = False
    stats, *_ = ctx._process_precomputed_pixels(req, "noqa")
    assert stats["valid_pixels"] == 2 and stats["nodata_pixels"] == 6
    assert stats["thermal"]["qa_mask_version"] is None
    assert stats["cloud_pct"] is None
    assert not stats["validated_raster_product"]["cloud_mask_applied"]


def test_calibrated_nonfinite_and_internal_mask(tmp_path, monkeypatch):
    ctx, req, _ = make_case(tmp_path, monkeypatch, True)
    with rasterio.open(tmp_path / "st.tif", "r+") as ds:
        arr = ds.read(1)
        arr[1, 2], arr[1, 3], arr[2, 1] = np.inf, np.nan, 299
        ds.write(arr, 1)
        valid = np.full(ds.shape, 255, dtype="uint8")
        valid[2, 1] = 0
        ds.write_mask(valid)
    req._landsat_st["checksum"] = None
    stats, *_ = ctx._process_precomputed_pixels(req, "finite")
    assert stats["valid_pixels"] == 1 and stats["mean"] == pytest.approx(EXPECTED)
