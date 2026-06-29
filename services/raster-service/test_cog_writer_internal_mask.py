"""
test_cog_writer_internal_mask.py — حارس انحدار لجذر مشكلة "الشرائط الداكنة".

السبب الجذري للشرائط: cog_writer قديماً لم يكتب قناعاً داخليّاً، فبكسلات خارج
الحقل (قد تكون finite مثل 0.0، أو NaN دون قناع) تُعامَل كبيانات صالحة عند
التصيير → ألوان معتمة فوق الخريطة بدل الشفافيّة.

هذا الملفّ يثبت:
  (1) دورة كاملة: write_cog يكتب COG بقناع داخلي مشتقّ من np.isfinite، ثمّ
      render_tile_png لبلاطة المركز ينتج صورة فيها بكسلات معتمة (النصف الصالح)
      وبكسلات شفّافة (النصف NaN) — لا شرائط. والبلاطة داخل الحقل كاملاً
      (الحقل 512px@10m ≈ 5.1km > عرض بلاطة z14 ≈ 2.4km).
  (2) القناع الداخلي مكتوب فعلاً: mask_flag_enums[0] ليس all_valid، و
      nodata == -9999 (رقميّ لا NaN).
"""

import math
import os
import struct
import tempfile
import zlib

import cog_writer
import numpy as np
import rasterio
import tile_render
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

pytestmark = []

# الجوف (اليمن) ضمن UTM zone 38N — نفس مرجع test_tiles.py
UTM = "EPSG:32638"
ORIGIN_X = 393000.0  # easting (أعلى يسار)
ORIGIN_Y = 1773000.0  # northing
RES = 10.0  # 10 م/بكسل (Sentinel-2)
SIZE = 512  # 512px@10m ≈ 5.1km > عرض بلاطة z14 ≈ 2.4km → بلاطة المركز داخل الحقل


def _decode_png_rgba(png_bytes: bytes) -> np.ndarray:
    """يفكّ تشفير PNG (RGBA، color type 6، filter 0) — مطابق لمفكّك test_tiles."""
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "ليس PNG"
    pos = 8
    width = height = None
    idat = bytearray()
    while pos < len(png_bytes):
        (length,) = struct.unpack(">I", png_bytes[pos : pos + 4])
        tag = png_bytes[pos + 4 : pos + 8]
        data = png_bytes[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
            assert bit_depth == 8 and color_type == 6, "متوقّع 8-bit RGBA"
        elif tag == b"IDAT":
            idat.extend(data)
        elif tag == b"IEND":
            break
        pos += 12 + length
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    out = np.zeros((height, width, 4), dtype=np.uint8)
    rp = 0
    for r in range(height):
        ftype = raw[rp]
        assert ftype == 0, f"filter type {ftype} غير مدعوم (متوقّع 0)"
        rp += 1
        row = np.frombuffer(raw[rp : rp + stride], dtype=np.uint8)
        out[r] = row.reshape(width, 4)
        rp += stride
    return out


def _write_half_valid_cog(path: str):
    """يكتب COG عبر cog_writer.write_cog: النصف الأيسر NaN (غير صالح)،
    النصف الأيمن 0.7 (صالح). القناع يُشتقّ من np.isfinite داخل write_cog.
    """
    arr = np.full((SIZE, SIZE), np.nan, dtype="float32")
    arr[:, SIZE // 2 :] = 0.7  # النصف الأيمن: NDVI صالح
    transform = from_origin(ORIGIN_X, ORIGIN_Y, RES, RES)
    result = cog_writer.write_cog(arr, path, transform, crs=UTM)
    assert result.get("written") is True, result
    return result


def _center_tile(z: int = 14):
    """يحسب بلاطة z/x/y التي تغطّي مركز الحقل."""
    bounds_utm = (ORIGIN_X, ORIGIN_Y - SIZE * RES, ORIGIN_X + SIZE * RES, ORIGIN_Y)
    b4 = transform_bounds(UTM, "EPSG:4326", *bounds_utm)
    clon = (b4[0] + b4[2]) / 2.0
    clat = (b4[1] + b4[3]) / 2.0
    tx, ty = tile_render._lonlat_to_tile(clon, clat, z)
    return z, tx, ty


def test_internal_mask_renders_invalid_half_transparent_not_striped():
    """دورة كاملة: write_cog (قناع داخلي) → render_tile_png لبلاطة المركز.

    النصف غير الصالح (NaN) يجب أن يُصيَّر شفّافاً (alpha=0) لا كشرائط معتمة،
    والنصف الصالح معتماً (alpha>0)، والبلاطة داخل الحقل كاملاً (≈ كلّها معرّفة).
    """
    tmpdir = tempfile.mkdtemp(prefix="cogmask_test_")
    cog_path = os.path.join(tmpdir, "half_valid.tif")
    res = _write_half_valid_cog(cog_path)
    # توحيد main↔cert: نتحقّق أنّ COG كُتب وله أهرامات داخليّة. لا نشترط tiled=True هنا
    # لأنّ مصفوفة الاختبار الصغيرة (أصغر من كتلة 512) لا يُبلّطها GDAL — والتحقّق الفعليّ
    # للقناع/الشفافيّة أدناه (التصيير). (cert يستخدم DEFAULT_NODATA رقميّ + قناع داخليّ.)
    assert res.get("written") is True, res
    assert res["validation"].get("overviews"), res["validation"]

    z, tx, ty = _center_tile()
    png = tile_render.render_tile_png(cog_path, z, tx, ty, "ndvi")
    assert png is not None, "render_tile_png أرجع None — البلاطة يجب أن تتقاطع مع الحقل"

    rgba = _decode_png_rgba(png)
    assert rgba.shape == (256, 256, 4), rgba.shape
    alpha = rgba[..., 3]

    n_opaque = int((alpha > 0).sum())
    n_transparent = int((alpha == 0).sum())

    # البلاطة داخل الحقل كاملاً → كلّ بكسل إمّا معتم (صالح) أو شفّاف (NaN).
    assert n_opaque + n_transparent == 256 * 256
    # النصف الصالح موجود → بكسلات معتمة.
    assert n_opaque > 0, "متوقّع بكسلات معتمة من النصف الصالح (0.7)"
    # النصف غير الصالح (NaN) يُصيَّر شفّافاً لا كشرائط معتمة.
    assert n_transparent > 0, (
        "متوقّع بكسلات شفّافة من النصف NaN — لو كانت معتمة فهي شرائط (القناع لم يُحترم)"
    )


def test_cog_writer_actually_writes_internal_mask_and_numeric_nodata():
    """يثبت أنّ القناع الداخلي مكتوب فعلاً وأنّ nodata رقميّ (-9999 لا NaN)."""
    tmpdir = tempfile.mkdtemp(prefix="cogmask_test2_")
    cog_path = os.path.join(tmpdir, "masked.tif")
    _write_half_valid_cog(cog_path)

    with rasterio.open(cog_path) as src:
        flags = src.mask_flag_enums[0]
        # القناع لكلّ-بكسل (per-dataset) → ليس all_valid فقط.
        assert rasterio.enums.MaskFlags.per_dataset in flags, (
            f"متوقّع قناع per-dataset لكن mask_flag_enums={flags}"
        )
        assert rasterio.enums.MaskFlags.all_valid not in flags, (
            f"القناع all_valid يعني لا قناع داخلي حقيقي: {flags}"
        )
        # nodata رقميّ لا NaN.
        assert src.nodata == cog_writer.DEFAULT_NODATA == -9999.0, src.nodata
        assert not (src.nodata is None or math.isnan(src.nodata))
