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
    with rasterio.open(path, "r+") as dst:
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
