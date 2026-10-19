"""Local real-library rendering witness, not a container or deployed-service receipt.

Run with titiler-core==0.22.4, rio-tiler==7.9.6, rasterio, httpx and Pillow.
PYTHONPATH=. python certification/evidence/cog_rendering_20261019/render_probe.py
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import io
import json
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from rasterio.transform import from_bounds
from titiler.core.factory import TilerFactory

from shared.gis.cog_display_policy import display_for_cog
from shared.gis.cog_tile_proxy import _validate_png_header


def main():
    versions = {
        p: importlib.metadata.version(p)
        for p in ("titiler-core", "rio-tiler", "rasterio", "numpy", "Pillow")
    }
    assert versions["titiler-core"] == "0.22.4"
    assert versions["rio-tiler"] == "7.9.6"
    app = FastAPI()
    app.include_router(TilerFactory().router, prefix="/cog")
    client = TestClient(app)
    policy = display_for_cog("ndvi")
    half_world = 20037508.342789244
    data = np.tile(np.linspace(-1, 1, 256, dtype="float32"), (256, 1))
    data[:16, :] = -9999
    data[16:32, :] = np.nan
    data[64:96, 64:96] = 0.25
    variants = {
        "week_a": data,
        "week_b": data.copy(),
        "all_nodata": np.full_like(data, -9999),
        "constant": np.full_like(data, 0.25),
    }
    variants["week_b"][128:, :] = 0.8
    results, images = {}, {}
    with tempfile.TemporaryDirectory(prefix="sahool-cog-render-") as tmp:
        for name, values in variants.items():
            path = Path(tmp) / f"{name}.tif"
            mask = np.isfinite(values) & (values != -9999)
            spec = importlib.util.spec_from_file_location(
                "probe_cog_writer",
                Path(__file__).resolve().parents[3] / "services/raster-service/cog_writer.py",
            )
            writer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(writer)
            written = writer.write_cog(
                values,
                str(path),
                from_bounds(-half_world, -half_world, half_world, half_world, 256, 256),
                crs="EPSG:3857",
                nodata=-9999,
            )
            assert written["written"] is True
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            response = client.get(
                "/cog/tiles/WebMercatorQuad/0/0/0.png",
                params={"url": str(path), "colormap_name": "viridis", "rescale": policy["rescale"]},
            )
            assert response.status_code == 200, (name, response.text[:200])
            _validate_png_header(response.content)
            rgba = np.array(Image.open(io.BytesIO(response.content)).convert("RGBA"))
            images[name] = rgba
            assert hashlib.sha256(path.read_bytes()).hexdigest() == before
            with rasterio.open(path) as src:
                np.testing.assert_array_equal(src.read(1)[mask], values[mask])
                assert np.all(src.read(1)[~mask] == src.nodata)
            results[name] = {
                "source_sha256": before,
                "shape": list(rgba.shape),
                "opaque_pixels": int((rgba[..., 3] > 0).sum()),
                "colors": int(np.unique(rgba.reshape(-1, 4), axis=0).shape[0]),
                "source_unchanged": True,
            }
        assert np.all(images["week_a"][:32, :, 3] == 0)
        assert np.all(images["all_nodata"][..., 3] == 0)
        assert results["week_a"]["colors"] > 50
        np.testing.assert_array_equal(
            images["week_a"][64:96, 64:96], images["week_b"][64:96, 64:96]
        )
        np.testing.assert_array_equal(images["week_a"][80, 80], images["constant"][80, 80])
    print(
        json.dumps(
            {
                "scope": "local libraries; not Docker/staging/production",
                "versions": versions,
                "policy": policy,
                "cases": results,
                "same_value_same_color": True,
                "nodata_and_nan_transparent": True,
                "all_nodata_transparent": True,
                "scientific_pixels_unchanged": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
