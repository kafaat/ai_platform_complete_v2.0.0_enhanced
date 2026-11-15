"""Exact task previews use either the index palette or a local grayscale ramp."""

from io import BytesIO

import numpy as np
import pytest
import rasterio
import tile_render
from PIL import Image
from raster_api_models import IndicatorKind
from rasterio.transform import from_origin
from routers import cdse_tiles


@pytest.mark.parametrize("kind", list(IndicatorKind))
@pytest.mark.asyncio
async def test_catalog_task_preview(monkeypatch, tmp_path, kind):
    index = kind.value
    path = tmp_path / "source.tif"
    rgb = index == "truecolor"
    values = np.tile(np.arange(32), (32, 1)).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=3 if rgb else 1,
        dtype="uint8" if rgb else "float32",
        crs="EPSG:32638",
        transform=from_origin(500000, 2800000, 10, 10),
    ) as dst:
        for i in dst.indexes:
            dst.write((values * 6 if rgb else values).astype(dst.dtypes[0]), i)

    async def fetch(field, name, date, *, tenant_id, asset_id):
        assert (field, name, date, asset_id) == ("wheat", index, "2026-10-01", 81)
        return {"cog_url": str(path), "acquisition_date": date}

    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", fetch)
    res = await cdse_tiles._persisted_thumbnail("wheat", index, "2026-10-01", 64, 81)
    if index == "et_inputs":
        assert res.status_code == 404
        return
    assert res.status_code == 200 and res.headers["X-Raster-Asset-Id"] == "81"
    pixels = np.array(Image.open(BytesIO(res.body)).convert("RGBA"))
    visible = pixels[pixels[:, :, 3] > 0]
    assert len(visible) > 0
    if res.headers["X-Preview-Style"] == "relative":
        assert np.array_equal(visible[:, 0], visible[:, 1])
        assert np.array_equal(visible[:, 0], visible[:, 2])
        assert int(np.ptp(visible[:, 0])) == 255
