"""قناع المضلّع لا يُتلِف الراستر الذي يقصّه (G-CLIP-1 · G-CLIP-2، تدقيق 2026-10-27).

الخلل (مقيس على ``5c7e1cb83``): ``apply_polygon_mask`` كان يُعيد كتابة الملفّ من
``src.profile`` وحده — والـprofile لا يحمل scale/offset ولا الوسوم ولا أوصاف النطاقات ولا
الأهرامات. فبعد قصّ نصف الحقل: scale 0.001/offset 2 ⇒ 1/0 (تتغيّر القيم الفيزيائيّة
المُفسَّرة)، الوصف والوسم يختفيان، والأهرامات ``[2, 4]`` ⇒ ``[]`` (لم يعد COG). ونوع
صحيح (uint16) كان ينهار بـ``TypeError`` لأنّ NaN لا يُخزَّن فيه، والمضلّع غير المتقاطع
يُعيد راستراً كلّه NaN بصمت رغم أنّ الـdocstring وعد بالرفع.

العقد المُثبَّت هنا:
  * القيم خارج المضلّع ⇒ nodata، وداخله كما هي؛ الأبعاد والـCRS والـaffine ثابتة.
  * scale/offset/units/الوسوم/الأوصاف/colorinterp تبقى، والأهرامات تُعاد بناؤها
    (بمستوياتها وبإعادة عيّنتها المُعلَنة)، وتخطيط COG يبقى COG.
  * الأنواع الصحيحة تُملأ بـnodata المُعلَن؛ وبلا nodata مُعلَن ⇒ رفض صريح قبل أيّ كتابة.
  * عدم التقاطع **صريح**: تُعيد الدالّة عدد بكسلات داخل المضلّع (0 = لا تقاطع) ولا
    ترفع — رفض المنتج الفارغ سلطةُ فحص المحتوى عند المُستدعي، وهو ما يُسند إليه
    إسنادُ «polygon_mask_removed_observations» في الإيصال المتين.
"""

from __future__ import annotations

import warnings

import cog_writer
import numpy as np
import pytest
import rasterio
import rasterio.shutil
import tile_render
from rasterio.enums import ColorInterp, Resampling
from rasterio.transform import from_bounds

pytestmark = pytest.mark.unit

TRANSFORM = from_bounds(44, 14, 45, 15, 8, 8)
WEST_HALF = {
    "type": "Polygon",
    "coordinates": [[[44, 14], [44.5, 14], [44.5, 15], [44, 15], [44, 14]]],
}
OUTSIDE = {
    "type": "Polygon",
    "coordinates": [[[46, 14], [47, 14], [47, 15], [46, 15], [46, 14]]],
}


def _scalar(path, *, dtype="float32", nodata=None, value=5):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=8,
        width=8,
        count=1,
        dtype=dtype,
        crs="EPSG:4326",
        transform=TRANSFORM,
        nodata=nodata,
    ) as dst:
        dst.write(np.full((1, 8, 8), value, dtype=dtype))
        dst.update_tags(scene="S2A_TEST_SCENE")
        dst.update_tags(1, band_role="ndvi")
        dst.scales = (0.001,)
        dst.offsets = (2.0,)
        dst.units = ("ratio",)
        dst.set_band_description(1, "physical-band")
        dst.build_overviews([2, 4], Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")
    return str(path)


def _mask(path, geom):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # تحذيرات rasterio الداخليّة (affine/خارج الحدود)
        return tile_render.apply_polygon_mask(path, geom)


def test_scalar_mask_preserves_scale_offset_tags_descriptions_and_overviews(tmp_path):
    path = _scalar(tmp_path / "ndvi.tif")
    _mask(path, WEST_HALF)
    with rasterio.open(path) as src:
        data = src.read(1)
        assert int(np.isfinite(data).sum()) == 32
        assert np.isnan(data[:, 4:]).all() and (data[:, :4] == 5).all()
        assert src.transform == TRANSFORM and src.crs.to_epsg() == 4326
        assert np.isnan(src.nodata)
        assert src.scales == (0.001,), "scale ضاع ⇒ القيم الفيزيائيّة تُفسَّر خطأً"
        assert src.offsets == (2.0,)
        assert src.units == ("ratio",)
        assert src.descriptions == ("physical-band",)
        assert src.tags()["scene"] == "S2A_TEST_SCENE"
        assert src.tags(1)["band_role"] == "ndvi"
        assert src.overviews(1) == [2, 4], "الأهرامات ضاعت ⇒ لم يعد COG"
        assert src.tags(ns="rio_overview")["resampling"] == "average"
        # الأهرامات **مُعادة البناء** من البيانات المقصوصة، لا منسوخة من الأصل.
        overview = src.read(1, out_shape=(4, 4))
        assert np.isnan(overview[:, 2:]).all() and np.isfinite(overview[:, :2]).all()


def test_integer_raster_is_filled_with_its_declared_nodata_not_nan(tmp_path):
    path = _scalar(tmp_path / "dn.tif", dtype="uint16", nodata=0, value=1234)
    inside = _mask(path, WEST_HALF)
    assert inside == 32
    with rasterio.open(path) as src:
        assert src.dtypes == ("uint16",) and src.nodata == 0
        data = src.read(1)
        assert (data[:, 4:] == 0).all() and (data[:, :4] == 1234).all()
        assert src.scales == (0.001,) and src.offsets == (2.0,)
        assert src.overviews(1) == [2, 4]


def test_integer_raster_without_nodata_is_refused_before_any_write(tmp_path):
    path = _scalar(tmp_path / "dn_no_nodata.tif", dtype="uint16", value=7)
    before = open(path, "rb").read()
    with pytest.raises(ValueError, match="nodata"):
        _mask(path, WEST_HALF)
    assert open(path, "rb").read() == before, "الرفض يجب أن يسبق إعادة الكتابة"


def test_non_intersecting_polygon_is_explicit_zero_not_silent(tmp_path):
    path = _scalar(tmp_path / "outside.tif")
    assert _mask(path, OUTSIDE) == 0
    with rasterio.open(path) as src:
        assert not np.isfinite(src.read(1)).any()
    assert _mask(_scalar(tmp_path / "half.tif"), WEST_HALF) == 32


def test_source_nodata_inside_polygon_stays_nodata(tmp_path):
    path = _scalar(tmp_path / "holes.tif", nodata=-9999.0)
    with rasterio.open(path, "r+") as dst:
        data = dst.read(1)
        data[0, 0] = -9999.0
        dst.write(data, 1)
    assert _mask(path, WEST_HALF) == 32
    with rasterio.open(path) as src:
        assert int(np.isfinite(src.read(1)).sum()) == 31


def test_cog_layout_survives_the_rewrite(tmp_path):
    plain = _scalar(tmp_path / "plain.tif")
    cog = str(tmp_path / "cog.tif")
    rasterio.shutil.copy(plain, cog, driver="COG", BLOCKSIZE=256, OVERVIEWS="NONE")
    with rasterio.open(cog) as src:
        assert src.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG"
    _mask(cog, WEST_HALF)
    with rasterio.open(cog) as src:
        assert src.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG"
        assert int(np.isfinite(src.read(1)).sum()) == 32
        assert src.scales == (0.001,) and src.descriptions == ("physical-band",)


def test_rgba_mask_preserves_alpha_interpretation_and_overviews(tmp_path):
    path = str(tmp_path / "truecolor.tif")
    # write_rgba_cog يبني أهرامات 2..16 ⇒ يلزم ٣٢ بكسلاً على الأقلّ.
    rgba = np.full((4, 32, 32), 200, dtype="uint8")
    rgba[3] = 255
    assert cog_writer.write_rgba_cog(rgba, path, from_bounds(44, 14, 45, 15, 32, 32))["written"]
    # write_rgba_cog writes a real COG layout (ST-01), and GDAL refuses an in-place
    # update of a COG unless told the layout may break. Only this fixture tag is written.
    with rasterio.open(path, "r+", IGNORE_COG_LAYOUT_BREAK="YES") as dst:
        dst.update_tags(scene="S2A_TEST_SCENE")
    with rasterio.open(path) as src:
        overviews = src.overviews(1)
        assert overviews
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tile_render.apply_polygon_mask_rgba(path, WEST_HALF)
    with rasterio.open(path) as src:
        alpha = src.read(4)
        assert (alpha[:, 16:] == 0).all() and (alpha[:, :16] == 255).all()
        assert src.colorinterp[3] == ColorInterp.alpha
        assert src.overviews(1) == overviews
        assert src.tags()["scene"] == "S2A_TEST_SCENE"
        assert src.tags(ns="rio_overview")["resampling"] == "nearest"


def test_band_statistics_from_before_the_mask_are_not_carried_over(tmp_path):
    # وسوم STATISTICS_* مُشتقّة من البيانات: بعد قصّ نصف الراستر تصير كاذبة (المتوسّط
    # ونسبة الصالح)، وQGIS/GDAL يمدّان العرض بها. لا تُنسخ؛ وسوم النطاق الوصفيّة تبقى.
    path = _scalar(tmp_path / "stats.tif", value=50)
    with rasterio.open(path, "r+") as dst:
        dst.update_tags(
            1,
            STATISTICS_MINIMUM="50",
            STATISTICS_MAXIMUM="50",
            STATISTICS_MEAN="50",
            STATISTICS_STDDEV="0",
            STATISTICS_VALID_PERCENT="100",
        )
    _mask(path, WEST_HALF)
    with rasterio.open(path) as src:
        band_tags = src.tags(1)
        stale = sorted(k for k in band_tags if k.startswith("STATISTICS_"))
        assert stale == [], f"إحصاءات ما قبل القناع بقيت: {stale}"
        assert band_tags["band_role"] == "ndvi"


def test_overview_resampling_tag_is_case_insensitive(tmp_path):
    # GDAL يقبل «AVERAGE» و«average»؛ Resampling[...] حسّاس لحالة الأحرف فكان KeyError
    # يُسقط البلاطة fail-closed بلا سبب.
    path = _scalar(tmp_path / "upper.tif")
    with rasterio.open(path, "r+") as dst:
        dst.update_tags(ns="rio_overview", resampling="AVERAGE")
    assert _mask(path, WEST_HALF) == 32
    with rasterio.open(path) as src:
        assert src.overviews(1) == [2, 4]
        assert src.tags(ns="rio_overview")["resampling"] == "average"


def _bounded_source(monkeypatch, path, *, fail_after=None):
    """Observe production reads without substituting pixels or the destination."""
    original_open = rasterio.open
    reads = []

    class Reader:
        def __init__(self, source):
            self.source = source

        def __getattr__(self, name):
            return getattr(self.source, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.source.close()

        def read(self, *args, **kwargs):
            window = kwargs.get("window")
            assert window is not None, "full raster read"
            assert window.height <= 3 and window.width <= 3
            reads.append(window)
            if fail_after is not None and len(reads) > fail_after:
                raise OSError("injected late window failure")
            return self.source.read(*args, **kwargs)

    def opened(filename, *args, **kwargs):
        source = original_open(filename, *args, **kwargs)
        if str(filename) == str(path) and not args and kwargs.get("mode", "r") == "r":
            return Reader(source)
        return source

    monkeypatch.setattr(tile_render, "MAX_READ_DIM", 3)
    monkeypatch.setattr(rasterio, "open", opened)
    return reads


def test_content_observation_counts_masked_integer_exactly_in_bounded_windows(
    tmp_path, monkeypatch
):
    path = _scalar(tmp_path / "integer.tif", dtype="uint16", nodata=0)
    with rasterio.open(path, "r+") as dst:
        values = dst.read(1)
        values[0, 0] = 0
        dst.write(values, 1)
    reads = _bounded_source(monkeypatch, path)
    assert tile_render.raster_content_observation(path) == {
        "readable": True,
        "observable_pixels": 63,
        "field_shape_eligible": True,
    }
    assert len(reads) == 9


def test_content_observation_discards_partial_counts_on_late_failure(tmp_path, monkeypatch):
    path = _scalar(tmp_path / "failure.tif")
    _bounded_source(monkeypatch, path, fail_after=1)
    assert tile_render.raster_content_observation(path) == {
        "readable": False,
        "observable_pixels": None,
    }


def test_polygon_reads_are_bounded_and_preserve_mode(tmp_path, monkeypatch):
    path = _scalar(tmp_path / "windows.tif")
    import os
    import stat

    os.chmod(path, 0o640)
    with monkeypatch.context() as scoped:
        reads = _bounded_source(scoped, path)
        assert _mask(path, WEST_HALF) == 32
        assert len(reads) == 9
    with rasterio.open(path) as src:
        assert src.read(1, masked=True).count() == 32
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o640
    assert not list(tmp_path.glob(".polygon-mask-*"))


def test_late_polygon_read_failure_preserves_original_bytes(tmp_path, monkeypatch):
    path = _scalar(tmp_path / "failure.tif")
    before = open(path, "rb").read()
    _bounded_source(monkeypatch, path, fail_after=1)
    with pytest.raises(OSError, match="late window"):
        _mask(path, WEST_HALF)
    assert open(path, "rb").read() == before
    assert not list(tmp_path.glob(".polygon-mask-*"))


def test_cog_conversion_failure_preserves_original_bytes(tmp_path, monkeypatch):
    plain = _scalar(tmp_path / "plain.tif")
    path = str(tmp_path / "cog.tif")
    rasterio.shutil.copy(plain, path, driver="COG", BLOCKSIZE=256)
    before = open(path, "rb").read()

    def failed(*args, **kwargs):
        raise OSError("injected COG conversion failure")

    monkeypatch.setattr(rasterio.shutil, "copy", failed)
    with pytest.raises(OSError, match="COG conversion"):
        _mask(path, WEST_HALF)
    assert open(path, "rb").read() == before
    assert not list(tmp_path.glob(".polygon-mask-*"))


def test_existing_internal_mask_survives_forced_external_mask_environment(tmp_path):
    path = _scalar(tmp_path / "masked.tif")
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True), rasterio.open(path, "r+") as dst:
        valid = np.full((8, 8), 255, dtype="uint8")
        valid[1, 1] = 0
        dst.write_mask(valid)
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False):
        assert _mask(path, WEST_HALF) == 32
    with rasterio.open(path) as src:
        assert src.read(1, masked=True).count() == 31
    assert not (tmp_path / "masked.tif.msk").exists()


def test_rgba_polygon_reads_are_bounded_and_keep_source_mask(tmp_path, monkeypatch):
    path = str(tmp_path / "rgba.tif")
    with (
        rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True),
        rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=8,
            height=8,
            count=4,
            dtype="uint8",
            crs="EPSG:4326",
            transform=TRANSFORM,
        ) as dst,
    ):
        values = np.full((4, 8, 8), 255, dtype="uint8")
        values[3, 0, 0] = 0
        dst.write(values)
        dst.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue, ColorInterp.alpha)
        valid = np.full((8, 8), 255, dtype="uint8")
        valid[1, 1] = 0
        dst.write_mask(valid)
    with monkeypatch.context() as scoped:
        reads = _bounded_source(scoped, path)
        tile_render.apply_polygon_mask_rgba(path, WEST_HALF)
        assert len(reads) == 9
    with rasterio.open(path) as src:
        assert np.count_nonzero(src.read(4)) == 30
        assert np.count_nonzero(src.dataset_mask()) == 30


def test_existing_external_mask_does_not_override_new_polygon_validity(tmp_path):
    path = _scalar(tmp_path / "external.tif", dtype="uint16", nodata=0)
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False), rasterio.open(path, "r+") as dst:
        valid = np.full((8, 8), 255, dtype="uint8")
        valid[1, 1] = 0
        dst.write_mask(valid)
    assert (tmp_path / "external.tif.msk").exists()
    _mask(path, WEST_HALF)
    with rasterio.open(path) as src:
        assert src.read(1, masked=True).count() == 31


def test_metadata_failure_after_pixels_preserves_original_bytes(tmp_path, monkeypatch):
    path = _scalar(tmp_path / "metadata-failure.tif")
    before = open(path, "rb").read()
    original = tile_render._raster_metadata

    def invalid_overview(source):
        metadata = original(source)
        metadata["overview_tags"] = {"resampling": "invalid-resampling"}
        return metadata

    monkeypatch.setattr(tile_render, "_raster_metadata", invalid_overview)
    with pytest.raises(KeyError, match="invalid-resampling"):
        _mask(path, WEST_HALF)
    assert open(path, "rb").read() == before
    assert not list(tmp_path.glob(".polygon-mask-*"))
