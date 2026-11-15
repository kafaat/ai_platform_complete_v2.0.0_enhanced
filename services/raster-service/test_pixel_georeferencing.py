"""Verify field pixel lookup at WGS84 pins through the production route."""

from datetime import date

import numpy as np
import pytest
import rasterio
from fastapi import HTTPException
from rasterio.transform import from_origin
from rasterio.warp import transform
from routers import fields


async def lookup(monkeypatch, path, lon, lat, index="ndvi"):
    async def allow(*args, **kwargs):
        return None

    async def layer(*args):
        return {"cog_url": str(path), "acquisition_date": "2024-03-07"}

    monkeypatch.setattr(fields, "_require_field_tenant", allow)
    monkeypatch.setattr(fields, "_resolve_field_layer", layer)
    return await fields.field_pixel_value(
        "pivot", lon=lon, lat=lat, index=index, date="2024-03-07", v=None
    )


def write(path, crs, affine, count=1):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=3,
        count=count,
        crs=crs,
        transform=affine,
        dtype="float32",
    ) as ds:
        ds.write(np.broadcast_to(np.arange(6, dtype="float32").reshape(2, 3), (count, 2, 3)))


@pytest.mark.asyncio
async def test_pin_requires_a_known_crs(tmp_path, monkeypatch):
    path = tmp_path / "unknown.tif"
    write(path, None, from_origin(44, 16, 0.01, 0.01))
    with pytest.raises(HTTPException) as error:
        await lookup(monkeypatch, path, 44.005, 15.995)
    assert error.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("index", ["truecolor", "ndvi"])
async def test_pin_does_not_treat_red_channel_as_an_index(tmp_path, monkeypatch, index):
    path = tmp_path / "rgb.tif"
    write(path, "EPSG:4326", from_origin(44, 16, 0.01, 0.01), count=3)
    with pytest.raises(HTTPException) as error:
        await lookup(monkeypatch, path, 44.005, 15.995, index=index)
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_projected_pin_selects_correct_cell_and_preserves_zero(tmp_path, monkeypatch):
    path = tmp_path / "utm.tif"
    affine = from_origin(450000, 1800000, 20, 20)
    write(path, "EPSG:32638", affine)
    for col, row, expected in [(0, 0, 0), (2, 1, 5)]:
        x, y = affine * (col + 0.5, row + 0.5)
        lon, lat = transform("EPSG:32638", "EPSG:4326", [x], [y])
        result = await lookup(monkeypatch, path, lon[0], lat[0])
        assert result["valid"] and result["value"] == expected
    x, y = affine * (3.01, 1.5)
    lon, lat = transform("EPSG:32638", "EPSG:4326", [x], [y])
    with pytest.raises(HTTPException) as error:
        await lookup(monkeypatch, path, lon[0], lat[0])
    assert error.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("acquired", ["2024-03-08T01:00:00+03:00", date(2024, 3, 7)])
async def test_latest_tilejson_pins_utc_day_and_keeps_internal_uri_private(monkeypatch, acquired):
    from urllib.parse import parse_qs, urlsplit

    async def allow(*args, **kwargs):
        return None

    async def layer(*args):
        return {
            "cog_url": "/private/path/fixture.tif",
            "acquisition_date": acquired,
            "bounds_4326": [44, 15, 45, 16],
        }

    monkeypatch.setattr(fields, "_require_field_tenant", allow)
    monkeypatch.setattr(fields, "_resolve_field_layer", layer)
    tj = await fields.field_tilejson("pivot", index="msi", date="latest", v=None)
    params = parse_qs(urlsplit(tj["tiles"][0]).query)
    assert tj["resolved_date"] == "2024-03-07"
    assert params["date"] == ["2024-03-07"]
    assert params["v"] == [tj["cache_version"]]
    assert "private/path" not in tj["cache_version"]
