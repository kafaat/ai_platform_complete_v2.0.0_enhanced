"""حارس انحدار: COG الصورة الخام (truecolor) يجب أن يصرّح PHOTOMETRIC=RGB على القرص.

الجذر: ``RGBA_COG_PROFILE`` كان بلا مفتاح ``photometric`` ⇒ GDAL يكتب الافتراضيّ
MINISBLACK (قناة لونيّة واحدة). ضبط ``dst.colorinterp`` بعد الإنشاء يوسم ألفا فقط،
فتصبح على القرص: 1 قناة لونيّة + 1 عيّنة إضافيّة = 2 ≠ 4 عيّنات ⇒ عند القراءة يحذّر
GDAL («Sum of Photometric type-related color channels and ExtraSamples doesn't match
SamplesPerPixel») ويعيد تعريف نطاقات RGB كـExtraSamples — فقدان تفسير اللون لأيّ
مستهلِك يعتمد GDAL (thumbnail، gdalinfo، أدوات خارجيّة). بعض إصدارات GDAL تنشر وسم
PHOTOMETRIC من colorinterp فتخفي العيب محلّيّاً؛ الإصلاح الحتميّ عبر الإصدارات: تصريح
``photometric="RGB"`` **وقت الإنشاء** (+ ``alpha="YES"`` للنطاق الرابع).

هذه اختبارات سلوكيّة تثبت على **ملفّ COG ناتج فعليّاً** (لا مجرّد وجود قيم في القاموس):
عدد النطاقات، تفسير اللون RGBA، وسم PHOTOMETRIC=RGB (tag 262)، غياب تحذير GDAL عند
الفتح، والشفافيّة خارج AOI مقابل قابليّة قراءة RGB داخلها.
"""

from __future__ import annotations

import io
import logging
import os
import struct
import tempfile
from pathlib import Path

import cog_writer
import numpy as np
import rasterio
from rasterio.enums import ColorInterp
from rasterio.transform import from_origin

pytestmark = []

UTM = "EPSG:32638"  # الجوف (اليمن) — مطابق لبقيّة اختبارات الرستر
ORIGIN_X = 393000.0
ORIGIN_Y = 1773000.0
RES = 10.0
SIZE = 64

# PhotometricInterpretation (TIFF tag 262): 1=BlackIsZero (MINISBLACK)، 2=RGB.
PHOTOMETRIC_RGB = 2


def _photometric_tag(path: str) -> int | None:
    """يقرأ وسم TIFF 262 (PhotometricInterpretation) مباشرةً من الملفّ — لأنّ rasterio
    لا يُرجِع ``photometric`` في ``profile`` عند القراءة."""
    data = Path(path).read_bytes()
    if data[:2] not in (b"II", b"MM"):
        return None
    bo = "<" if data[:2] == b"II" else ">"
    (ifd_off,) = struct.unpack(bo + "I", data[4:8])
    (count,) = struct.unpack(bo + "H", data[ifd_off : ifd_off + 2])
    for i in range(count):
        entry = ifd_off + 2 + i * 12
        tag, _typ, _cnt = struct.unpack(bo + "HHI", data[entry : entry + 8])
        if tag == 262:
            return struct.unpack(bo + "H", data[entry + 8 : entry + 10])[0]
    return None


def _rgba_array() -> np.ndarray:
    """RGBA (4,H,W): RGB ثابت، وألفا معتمة (255) داخل صندوق مركزيّ وشفّافة (0) خارجه."""
    arr = np.zeros((4, SIZE, SIZE), dtype=np.uint8)
    arr[0] = 200  # R
    arr[1] = 120  # G
    arr[2] = 60  # B
    lo, hi = SIZE // 4, 3 * SIZE // 4
    arr[3, lo:hi, lo:hi] = 255  # ألفا معتمة داخل AOI فقط
    return arr


def _transform():
    return from_origin(ORIGIN_X, ORIGIN_Y, RES, RES)


def _open_capturing_gdal_warnings(path: str):
    """يفتح COG مع التقاط تحذيرات GDAL المُوجَّهة عبر مُسجّل ``rasterio._env``
    (تحذير PHOTOMETRIC يصل كـCPLE_AppDefined عبر التسجيل لا عبر warnings)."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("rasterio._env")
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        with rasterio.open(path) as src:
            snapshot = {
                "count": src.count,
                "colorinterp": list(src.colorinterp),
                "band_last": src.read(src.count),
                "rgb": src.read([1, 2, 3]) if src.count >= 3 else None,
            }
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)
    warnings_text = buf.getvalue()
    photometric_warnings = [
        line
        for line in warnings_text.splitlines()
        if "Photometric" in line or "ExtraSamples" in line
    ]
    return snapshot, photometric_warnings


def test_rgba_cog_declares_rgb_photometric_alpha_and_transparency():
    """4 نطاقات RGBA: PHOTOMETRIC=RGB على القرص، النطاق 4 ألفا، لا تحذير GDAL، وشفافيّة
    صحيحة (شفّاف خارج AOI، RGB مقروء داخلها)."""
    tmp = os.path.join(tempfile.mkdtemp(prefix="rgba_cog_photo_"), "tc.tif")
    res = cog_writer.write_rgba_cog(_rgba_array(), tmp, _transform(), crs=UTM)
    assert res.get("written") is True, res
    assert res.get("bands") == 4, res

    # PHOTOMETRIC=RGB مكتوب فعليّاً على القرص (الإصلاح الحتميّ عبر الإصدارات).
    assert _photometric_tag(tmp) == PHOTOMETRIC_RGB, (
        f"متوقّع PhotometricInterpretation=RGB(2) لكن tag262={_photometric_tag(tmp)}"
    )

    snap, photometric_warnings = _open_capturing_gdal_warnings(tmp)
    assert snap["count"] == 4, snap["count"]
    # النطاقات 1–3 = RGB، النطاق 4 = ألفا.
    assert snap["colorinterp"][:3] == [
        ColorInterp.red,
        ColorInterp.green,
        ColorInterp.blue,
    ], snap["colorinterp"]
    assert snap["colorinterp"][3] == ColorInterp.alpha, snap["colorinterp"]
    # لا تحذير PHOTOMETRIC/ExtraSamples عند الفتح.
    assert not photometric_warnings, photometric_warnings

    # الشفافيّة: بكسل خارج AOI شفّاف (ألفا=0)، وداخلها معتم (ألفا=255) وRGB مقروء.
    alpha = snap["band_last"]
    assert int(alpha[0, 0]) == 0, "متوقّع بكسل شفّاف خارج AOI"
    cx = cy = SIZE // 2
    assert int(alpha[cy, cx]) == 255, "متوقّع بكسل معتم داخل AOI"
    rgb = snap["rgb"]
    assert tuple(int(rgb[b, cy, cx]) for b in range(3)) == (200, 120, 60), (
        "RGB داخل AOI يجب أن يكون مقروءاً بقيمه الأصليّة"
    )


def test_three_band_rgb_cog_declares_rgb_photometric():
    """3 نطاقات RGB (بلا ألفا): PHOTOMETRIC=RGB أيضاً، لا تحذير، تفسير RGB سليم."""
    arr = _rgba_array()[:3]  # RGB فقط
    tmp = os.path.join(tempfile.mkdtemp(prefix="rgb_cog_photo_"), "rgb.tif")
    res = cog_writer.write_rgba_cog(arr, tmp, _transform(), crs=UTM)
    assert res.get("written") is True, res
    assert res.get("bands") == 3, res
    assert _photometric_tag(tmp) == PHOTOMETRIC_RGB, _photometric_tag(tmp)

    snap, photometric_warnings = _open_capturing_gdal_warnings(tmp)
    assert snap["count"] == 3, snap["count"]
    assert snap["colorinterp"] == [
        ColorInterp.red,
        ColorInterp.green,
        ColorInterp.blue,
    ], snap["colorinterp"]
    assert not photometric_warnings, photometric_warnings


def test_source_sets_photometric_rgb_at_creation():
    """حارس ساكن: يمنع رجوع الإصلاح — المصدر يجب أن يصرّح ``photometric="RGB"``
    (والنطاق الرابع ``alpha``) وقت الإنشاء لا الاعتماد على انتشار colorinterp."""
    src = Path(cog_writer.__file__).read_text(encoding="utf-8")
    has_photometric_rgb = (
        'profile["photometric"] = "RGB"' in src  # الشكل الحاليّ (إسناد وقت الإنشاء)
        or '"photometric": "RGB"' in src  # أو ضمن قاموس البروفايل
        or "'photometric': 'RGB'" in src
    )
    assert has_photometric_rgb, "cog_writer يجب أن يضبط photometric=RGB صراحةً"
    has_alpha_yes = (
        'profile["alpha"] = "YES"' in src or '"alpha": "YES"' in src or "'alpha': 'YES'" in src
    )
    assert has_alpha_yes, "cog_writer يجب أن يوسم النطاق الرابع alpha=YES للـRGBA"
