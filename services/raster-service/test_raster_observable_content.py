"""حارس ``IMAGERY-BLANK-THUMBNAIL-01``: راستر بلا مشاهدة لا يدخل الكاش.

الجذر (مُثبَت بقراءة تدفّق التحكّم في ``raster_cdse_tile_runtime.ensure_field_cog``):
فروع الفشل كلّها تُنهي بـ``return None`` **قبل** سطر الكاش، فالفشل لا يُخزَّن أصلاً.
ما كان يُخزَّن أخطر: بين ``tf.write(geotiff_bytes)`` وسطر الكاش **لا يوجد أيّ تحقّق من
المحتوى**. وحين تُعيد CDSE استجابة ٢٠٠ بـGeoTIFF سليم البنية وفارغ البكسلات — وهو ما
يحدث حين لا يقع مرور قمر داخل النافذة المطلوبة — تُكتب البايتات وينجح عليها القناع،
فيُخزَّن **فراغ صالح البنية** ساعةً كاملة (``_t.monotonic() + 3600.0``). كلّ طلب لاحق
لنفس المفتاح يستهلك ذلك الفراغ بلا إعادة سؤال، فيبقى العطل ظاهراً حتّى بعد نشر إصلاح.

لذلك الاختبارات هنا **سلوكيّة على ملفّات راستر ناتجة فعليّاً** لا على قيم قاموس: تُبنى
الحالات (صالح · كلّه NaN · مُقنَّع بالكامل · ١×١ · تالف) وتُقاس النتيجة.

حدّ صريح: هذا الحارس يقيس **وجود مشاهدة**، لا جودتها. سلسلة كلّها NaN تعني «لا مشاهدة»
لا «مشاهدة رديئة» — والتمييز مقصود كي لا يتحوّل الفحص إلى بوّابة جودة صامتة.
"""

from __future__ import annotations

import numpy as np
import pytest
import tile_render
from rasterio.transform import from_origin

rasterio = pytest.importorskip("rasterio")

pytestmark = pytest.mark.unit

_TRANSFORM = from_origin(500000.0, 2800000.0, 10.0, 10.0)
_CRS = "EPSG:32638"


def _write(path, array, *, dtype, count, nodata=None, alpha_band=False, mask=None):
    """يكتب GeoTIFF حقيقيّاً على القرص ويُعيد مساره.

    ``mask``: قناع داخليّ (``write_mask``) — سلطة صلاحيّة **ثالثة** غير ألفا وغير
    ``nodata``. لا يكتبه ``_index``/``_rgba`` أعلاه، ولذلك يُمرَّر صراحةً في الحالات
    التي تقيسه.
    """
    profile = {
        "driver": "GTiff",
        "height": array.shape[-2],
        "width": array.shape[-1],
        "count": count,
        "dtype": dtype,
        "crs": _CRS,
        "transform": _TRANSFORM,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    if alpha_band:
        profile["photometric"] = "RGB"
        profile["alpha"] = "YES"
    with rasterio.open(path, "w", **profile) as dst:
        if count == 1:
            dst.write(array, 1)
        else:
            for band in range(count):
                dst.write(array[band], band + 1)
        if mask is not None:
            dst.write_mask(mask.astype("uint8"))
    return str(path)


def _rgba(tmp_path, alpha_value, name="rgba.tif"):
    arr = np.zeros((4, 32, 32), dtype="uint8")
    arr[0], arr[1], arr[2] = 90, 120, 70
    arr[3] = alpha_value
    return _write(tmp_path / name, arr, dtype="uint8", count=4, alpha_band=True)


def _index(tmp_path, values, name="index.tif"):
    return _write(tmp_path / name, values, dtype="float32", count=1, nodata=float("nan"))


def test_valid_index_raster_is_observable(tmp_path):
    """مؤشّر بقيم محدودة ⇒ مشاهدة حقيقيّة ⇒ يُخزَّن."""
    values = np.full((32, 32), 0.42, dtype="float32")
    assert tile_render.raster_has_observable_content(_index(tmp_path, values)) is True


def test_all_nan_index_raster_is_not_observable(tmp_path):
    """كلّه NaN ⇒ لا مشاهدة — هذه هي الحالة التي كانت تُجمَّد ساعةً."""
    values = np.full((32, 32), np.nan, dtype="float32")
    assert tile_render.raster_has_observable_content(_index(tmp_path, values)) is False


def test_a_single_valid_pixel_is_enough(tmp_path):
    """بكسل صالح واحد يكفي: الحارس يقيس وجود مشاهدة لا نسبة تغطية."""
    values = np.full((32, 32), np.nan, dtype="float32")
    values[5, 7] = -0.13
    assert tile_render.raster_has_observable_content(_index(tmp_path, values)) is True


def test_fully_masked_rgba_is_not_observable(tmp_path):
    """RGBA بألفا صفر بالكامل ⇒ لا بكسل مرئيّ ⇒ لا يُخزَّن."""
    assert tile_render.raster_has_observable_content(_rgba(tmp_path, 0)) is False


def test_rgba_with_any_opaque_pixel_is_observable(tmp_path):
    """ألفا > 0 في بكسل واحد ⇒ مشاهدة."""
    arr = np.zeros((4, 32, 32), dtype="uint8")
    arr[0], arr[1], arr[2] = 90, 120, 70
    arr[3, 11, 3] = 255
    path = _write(tmp_path / "one_px.tif", arr, dtype="uint8", count=4, alpha_band=True)
    assert tile_render.raster_has_observable_content(path) is True


def test_rgba_colour_without_alpha_is_still_not_observable(tmp_path):
    """ألفا هي السلطة: بكسلات ملوّنة خلف ألفا صفر تبقى غير مرئيّة.

    يمنع هذا قبول استجابة تحمل لوناً «معقولاً» خارج القناع بينما الحقل كلّه شفّاف.
    """
    arr = np.zeros((4, 32, 32), dtype="uint8")
    arr[0], arr[1], arr[2] = 255, 255, 255
    arr[3] = 0
    path = _write(tmp_path / "colour_no_alpha.tif", arr, dtype="uint8", count=4, alpha_band=True)
    assert tile_render.raster_has_observable_content(path) is False


def test_one_by_one_raster_is_not_observable(tmp_path):
    """استجابة ١×١ ليست صورة حقل مهما كانت قيمتها صالحة."""
    values = np.full((1, 1), 0.5, dtype="float32")
    assert tile_render.raster_has_observable_content(_index(tmp_path, values)) is False


def test_unreadable_file_is_not_observable(tmp_path):
    """تالف/غير مقروء ⇒ False (fail-closed) — لا يُخزَّن المجهول."""
    corrupt = tmp_path / "corrupt.tif"
    corrupt.write_bytes(b"II*\x00 not a real tiff")
    assert tile_render.raster_has_observable_content(str(corrupt)) is False


def test_missing_file_is_not_observable(tmp_path):
    """ملفّ غائب ⇒ False بلا استثناء يتسرّب إلى المُستدعي."""
    assert tile_render.raster_has_observable_content(str(tmp_path / "nope.tif")) is False


# ── القناع الداخليّ وRGB بلا ألفا ────────────────────────────────────────────
# الحالات أدناه صحيحة في التنفيذ الحاليّ لكنّها كانت **بلا حارس**: صحّتها تأتي من
# دلالة القراءة المُقنَّعة (``read(1, masked=True)`` يطبّق قناع المجموعة) لا من فرع
# مكتوب لها. أي أنّ «تبسيطاً» لاحقاً للفرع قد يكسرها بصمت وكلّ الاختبارات خضراء.
# رُصِدت بمقارنة مع تنفيذ مستقلّ للفحص نفسه (لقطة 2026-07-28) يمرّ عبر
# ``dataset_mask()`` صراحةً؛ التنفيذان يتّفقان على النتائج، والفارق أنّ حالاتها كانت
# مُغطّاة وحالاتنا لا.


def test_rgb_without_an_alpha_band_is_observable(tmp_path):
    """ثلاثة نطاقات بلا ألفا: لا سلطة ألفا تُسأل، والقناع كلّه صالح ⇒ مشاهدة."""
    arr = np.full((3, 32, 32), 80, dtype="uint8")
    path = _write(tmp_path / "rgb.tif", arr, dtype="uint8", count=3)
    assert tile_render.raster_has_observable_content(path) is True


def test_rgb_masked_out_entirely_is_not_observable(tmp_path):
    """نفس الملفّ بقناع داخليّ كلّه صفر ⇒ لا بكسل صالح، ولو كانت الألوان «معقولة».

    بلا هذه الحالة يبقى مسار RGB (٣ نطاقات) بلا أيّ قياس: الفرع الوحيد المكتوب
    صراحةً هو RGBA بأربعة نطاقات uint8.
    """
    arr = np.full((3, 32, 32), 80, dtype="uint8")
    path = _write(
        tmp_path / "rgb_masked.tif",
        arr,
        dtype="uint8",
        count=3,
        mask=np.zeros((32, 32)),
    )
    assert tile_render.raster_has_observable_content(path) is False


def test_finite_values_behind_a_fully_invalid_mask_are_not_observable(tmp_path):
    """قيم محدودة تماماً خلف قناع داخليّ كلّه صفر ⇒ لا مشاهدة.

    ``nodata``/NaN ليسا سلطة الصلاحيّة الوحيدة؛ القناع الداخليّ سلطة مستقلّة، وبقيّة
    الحالات هنا تكتب NaN فقط فلا تقيسه.
    """
    values = np.ones((32, 32), dtype="float32")
    path = _write(
        tmp_path / "masked_index.tif",
        values,
        dtype="float32",
        count=1,
        mask=np.zeros((32, 32)),
    )
    assert tile_render.raster_has_observable_content(path) is False


def test_check_does_not_modify_the_raster(tmp_path):
    """الحارس **يقيس ولا يُعدِّل**: البايتات على القرص كما هي بعد الفحص."""
    values = np.full((32, 32), 0.31, dtype="float32")
    path = _index(tmp_path, values)
    before = open(path, "rb").read()
    tile_render.raster_has_observable_content(path)
    assert open(path, "rb").read() == before
