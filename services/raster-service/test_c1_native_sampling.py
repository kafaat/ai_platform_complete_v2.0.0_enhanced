"""End-to-end C1 sampling on real mixed-resolution TIFFs and independent arrays."""

from types import SimpleNamespace

import numpy as np
import pytest
import raster_pixel_processing
import raster_processing_runtime
import rasterio
import stac_c1_processing as c1
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from test_stac_c1_processing import scene as scene

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "index,coarse_band", [("ndre", "rededge"), ("ndmi", "swir1"), ("moisture", "swir1")]
)
def test_c1_ratio_uses_valid_fine_samples_on_coarse_band_grid(scene, tmp_path, index, coarse_band):
    data, _, paths = scene
    clip = transform_geom(
        "EPSG:32638",
        "EPSG:4326",
        {
            "type": "Polygon",
            "coordinates": [
                [
                    (500001, 1799681),
                    (500319, 1799681),
                    (500319, 1799999),
                    (500001, 1799999),
                    (500001, 1799681),
                ]
            ],
        },
    )
    # Four different 10 m DNs under each 20 m pixel. The numeric zero and
    # independently masked 9000 must both disappear before averaging.
    nir = np.tile(np.array([[2000, 0], [4000, 9000]], dtype="uint16"), (16, 16))
    valid = np.tile(np.array([[255, 255], [255, 0]], dtype="uint8"), (16, 16))
    valid[:2, :2] = 0
    for name in ("nir", "red", "green", "blue"):
        path = paths[data["bands_urls"][name]]
        with rasterio.open(path) as src:
            profile = src.profile
            scales, offsets = src.scales, src.offsets
        profile.update(width=32, height=32)
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(nir if name == "nir" else np.full((32, 32), 2000, dtype="uint16"), 1)
            dst.scales, dst.offsets = scales, offsets
            if name == "nir":
                dst.write_mask(valid)
    scl = np.tile(np.array([[4, 9], [6, 11]], dtype="uint16"), (8, 8))
    for name in ("rededge", "swir1", "swir2", "scl"):
        href = data["bands_urls"][name]
        with rasterio.open(paths[href], "r") as src:
            profile = src.profile
            scales, offsets = src.scales, src.offsets
        profile.update(width=16, height=16, transform=from_origin(500000, 1800000, 20, 20))
        with rasterio.open(paths[href], "w", **profile) as dst:
            dst.write(scl if name == "scl" else np.full((16, 16), 2000, dtype="uint16"), 1)
            dst.scales, dst.offsets = scales, offsets

    ctx = raster_processing_runtime.make_processing_context(upload_dir=str(tmp_path))
    ctx.object_store = SimpleNamespace(upload_cog=lambda path, key: "file://" + path)

    def verify(job, req):
        with rasterio.open(req.raster_url) as src:
            assert src.transform == from_origin(500000, 1800000, 20, 20)
            assert src.shape == (16, 16)
            a = src.read(req.bands.nir, masked=True)
            b = src.read(getattr(req.bands, coarse_band), masked=True)
            assert a.mask[0, 0] and a.mask.sum() == 1
            np.testing.assert_allclose(a.compressed(), 3000)
            np.testing.assert_array_equal(src.read(req.bands.scl), scl)
            # Calibrated fine mean = 0.2, coarse reflectance = 0.1.
            nir_refl = a * src.scales[req.bands.nir - 1] + src.offsets[req.bands.nir - 1]
            coarse_refl = (
                b * src.scales[getattr(req.bands, coarse_band) - 1]
                + src.offsets[getattr(req.bands, coarse_band) - 1]
            )
            np.testing.assert_allclose(
                ((nir_refl - coarse_refl) / (nir_refl + coarse_refl)).compressed(), 1 / 3, rtol=1e-6
            )
            assert req._spatial_sampling["native_band_resolution_m"]["nir"] == 10
            assert req._spatial_sampling["native_band_resolution_m"][coarse_band] == 20

        stats, _, _, product = raster_pixel_processing.process_pixels(ctx, req, job)
        assert stats["cloud_mask_sources"] == ["SCL"]
        assert product["cog_url"], stats["cog"]
        with rasterio.open(product["cog_url"].removeprefix("file://")) as cog:
            output = cog.read(1, masked=True)
            assert cog.res == (20, 20)
            assert output.count() > 0
            assert output.mask[0, 0]
            assert output.mask[scl == 9].all()
            np.testing.assert_allclose(output.compressed(), 1 / 3, rtol=2e-6)

    c1.process_c1_scene(
        data,
        index,
        "field",
        "tenant",
        None,
        clip,
        True,
        "job",
        run_processing=verify,
        out_dir=str(tmp_path),
        entry_point="test",
    )
    assert not list(tmp_path.glob("stac_c1_*"))


def test_c1_rejects_falsely_fine_rededge(scene, tmp_path):
    from radiometry_containment import RadiometryUnresolved

    data, clip, _ = scene
    with pytest.raises(RadiometryUnresolved):
        c1.process_c1_scene(
            data,
            "ndre",
            "field",
            "tenant",
            None,
            clip,
            True,
            "job",
            run_processing=lambda *_: pytest.fail("invalid spectral grid used"),
            out_dir=str(tmp_path),
            entry_point="test",
        )
    assert not list(tmp_path.glob("stac_c1_*"))


def test_c1_rejects_declared_resolution_conflicting_with_tiff(scene, tmp_path):
    from radiometry_containment import RadiometryUnresolved

    data, clip, _ = scene
    data["radiometry_context"]["assets"]["red"]["raster:bands"][0]["spatial_resolution"] = 20
    with pytest.raises(RadiometryUnresolved):
        c1.process_c1_scene(
            data,
            "ndvi",
            "field",
            "tenant",
            None,
            clip,
            True,
            "job",
            run_processing=lambda *_: pytest.fail("false STAC spacing used"),
            out_dir=str(tmp_path),
            entry_point="test",
        )
    assert not list(tmp_path.glob("stac_c1_*"))
