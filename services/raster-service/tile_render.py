"""
tile_render.py — تصيير بلاطات XYZ ديناميكيّة (TiTiler-style) من COG مقصوص.

يحسب حدود بلاطة slippy-map (z/x/y) في Web-Mercator (EPSG:3857)، يقرأ/يعيد
إسقاط COG المؤشّر إلى مصفوفة 256×256 لتلك البقعة، يطبّق خريطة ألوان (RGBA
lookup يدويّ — بلا matplotlib)، ويُرجِع بايتات PNG. البكسلات بلا بيانات
(NaN / خارج الحقل المقصوص) تصبح شفّافة تماماً (alpha=0).

لا يدّعي بيانات غير متوفّرة: عند تعذّر القراءة/التصيير يُرجِع None، والمسار
في main يخدم بلاطة شفّافة (لا 500).
"""

from __future__ import annotations

import math
import struct
import zlib

TILE_SIZE = 256
WEB_MERCATOR_R = 6378137.0
# نصف محيط الأرض بالمتر (حدّ Web-Mercator على ±)
_ORIGIN_SHIFT = math.pi * WEB_MERCATOR_R


# ─── حسابات slippy-map (XYZ → حدود EPSG:3857) ──────────────────────
def tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """حدود بلاطة XYZ في Web-Mercator (EPSG:3857) بالمتر.

    يُرجِع (minx, miny, maxx, maxy). يستخدم رياضيّات slippy-map القياسيّة:
    عدد البلاطات لكلّ محور = 2**z، والإحداثيّات من ‎-ORIGIN_SHIFT إلى +ORIGIN_SHIFT.
    """
    n = 2**z
    tile_span = (2.0 * _ORIGIN_SHIFT) / n
    minx = -_ORIGIN_SHIFT + x * tile_span
    maxx = -_ORIGIN_SHIFT + (x + 1) * tile_span
    # محور y في XYZ يبدأ من الأعلى (الشمال) إلى الأسفل
    maxy = _ORIGIN_SHIFT - y * tile_span
    miny = _ORIGIN_SHIFT - (y + 1) * tile_span
    return minx, miny, maxx, maxy


def _lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    """يحوّل lon/lat إلى رقم بلاطة (x, y) عند تكبير z (slippy-map قياسي)."""
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(max(-85.05112878, min(85.05112878, lat)))
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


# ─── خرائط الألوان (RGBA lookup يدويّ — بلا matplotlib) ─────────────
# تدرّج NDVI: أحمر (نبات ضعيف) → أصفر → أخضر (نبات قويّ).
_NDVI_STOPS = [
    (0.00, (165, 0, 38)),  # أحمر داكن
    (0.20, (215, 48, 39)),  # أحمر
    (0.35, (244, 109, 67)),  # برتقالي
    (0.50, (253, 174, 97)),  # برتقالي فاتح
    (0.60, (254, 224, 139)),  # أصفر
    (0.70, (217, 239, 139)),  # أخضر مصفرّ
    (0.80, (166, 217, 106)),  # أخضر فاتح
    (0.90, (102, 189, 99)),  # أخضر
    (1.00, (26, 152, 80)),  # أخضر داكن
]


def _interp_stops(t: float, stops) -> tuple[int, int, int]:
    """يستيفي لوناً من قائمة محطّات (position[0..1], (r,g,b)) عند t∈[0,1]."""
    if t <= stops[0][0]:
        return stops[0][1]
    if t >= stops[-1][0]:
        return stops[-1][1]
    for i in range(1, len(stops)):
        p0, c0 = stops[i - 1]
        p1, c1 = stops[i]
        if t <= p1:
            f = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return (
                int(round(c0[0] + (c1[0] - c0[0]) * f)),
                int(round(c0[1] + (c1[1] - c0[1]) * f)),
                int(round(c0[2] + (c1[2] - c0[2]) * f)),
            )
    return stops[-1][1]


# نطاق المؤشّر الافتراضي ومعكوسيّة التدرّج لكلّ مؤشّر.
# salinity/ndsi: قيمة عالية = أسوأ → نعكس التدرّج (عالٍ = أحمر).
_INDEX_DOMAIN = {
    "ndvi": (-0.2, 0.9, False),
    "evi": (-0.2, 0.9, False),
    "ndmi": (-0.3, 0.6, False),
    "ndwi": (-0.5, 0.5, False),
    "ndsi": (-0.1, 0.6, True),
    "salinity": (-0.1, 0.6, True),
    # المؤشّرات الموسّعة (Sprint 5b)
    "ndre": (-0.1, 0.6, False),  # red-edge — نطاق أضيق من NDVI
    "msavi": (-0.2, 0.9, False),  # مثل NDVI (تصحيح تربة)
    "moisture": (-0.3, 0.6, False),  # NDMI-style: عالٍ = رطب (أخضر)
}


def index_legend(index: str) -> dict:
    """Return honest rendering metadata for a raster index.

    The frontend uses this to keep the legend/range synchronized with the
    actual tile renderer. Unknown indices fall back to the renderer default.
    """
    vmin, vmax, invert = _INDEX_DOMAIN.get(index, (-0.2, 0.9, False))
    return {
        "index": index,
        "vmin": float(vmin),
        "vmax": float(vmax),
        "invert": bool(invert),
        "palette": "RdYlGn_reversed" if invert else "RdYlGn",
        "nodata_alpha": 0,
    }


def colorize(arr, index: str):
    """يحوّل مصفوفة مؤشّر (float، NaN=خارج الحقل) إلى مصفوفة RGBA uint8.

    NaN → (0,0,0,0) شفّاف. القيم الصالحة → تدرّج المؤشّر مع alpha=255.
    يُرجِع مصفوفة numpy بالشكل (H, W, 4).
    """
    import numpy as np

    vmin, vmax, invert = _INDEX_DOMAIN.get(index, (-0.2, 0.9, False))
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    finite = np.isfinite(arr)
    if not finite.any():
        return rgba  # كلّه شفّاف

    # طبّع إلى [0,1] ضمن النطاق
    norm = np.clip((arr - vmin) / (vmax - vmin), 0.0, 1.0)
    if invert:
        norm = 1.0 - norm

    # جدول lookup مسبق (256 درجة) لتسريع التلوين بلا حلقة لكلّ بكسل
    lut = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        lut[i] = _interp_stops(i / 255.0, _NDVI_STOPS)

    idx = np.zeros((h, w), dtype=np.uint8)
    idx[finite] = np.clip(np.round(norm[finite] * 255.0), 0, 255).astype(np.uint8)
    rgb = lut[idx]  # (H, W, 3)

    rgba[..., 0] = rgb[..., 0]
    rgba[..., 1] = rgb[..., 1]
    rgba[..., 2] = rgb[..., 2]
    rgba[..., 3] = np.where(finite, 255, 0).astype(np.uint8)
    return rgba


# ─── ترميز PNG (يدويّ بـzlib — بلا PIL في مسار التشغيل) ─────────────
def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png_rgba(rgba) -> bytes:
    """يرمّز مصفوفة RGBA uint8 (H, W, 4) إلى بايتات PNG (color type 6).

    ترميز يدويّ بـzlib — لا يحتاج PIL في مسار التشغيل. كلّ صفّ مسبوق بـ
    بايت filter=0 (None).
    """
    import numpy as np

    rgba = np.ascontiguousarray(rgba.astype(np.uint8))
    h, w = rgba.shape[0], rgba.shape[1]

    # افتراض filter 0 لكلّ صفّ
    raw = bytearray()
    row_bytes = rgba.reshape(h, w * 4)
    for r in range(h):
        raw.append(0)
        raw.extend(row_bytes[r].tobytes())

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit, RGBA
    idat = zlib.compress(bytes(raw), 9)
    return sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


# ─── التصيير الرئيسي: COG → بلاطة 256×256 PNG ──────────────────────
def render_tile_png(cog_path: str, z: int, x: int, y: int, index: str) -> bytes | None:
    """يصيّر بلاطة XYZ من COG مقصوص. يُرجِع بايتات PNG أو None عند التعذّر.

    الخطوات:
      1) احسب حدود البلاطة في EPSG:3857.
      2) أعد إسقاط COG (مصدره غالباً UTM) إلى مصفوفة 256×256 لتلك البقعة
         بـrasterio.warp.reproject (nearest — يحافظ على حدّة حواف الحقل).
      3) البكسلات بلا بيانات (NaN) → شفّافة. لوّن الباقي بتدرّج المؤشّر.
      4) رمّز PNG.

    None عند: غياب rasterio / ملفّ مفقود / لا تقاطع / فشل القراءة. المُستدعي
    يخدم بلاطة شفّافة عندها (لا 500).
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.warp import Resampling, reproject
    except Exception:  # noqa: BLE001 — rasterio غير متوفّر → fallback شفّاف
        return None

    minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)
    dst_crs = "EPSG:3857"
    dst_transform = from_bounds(minx, miny, maxx, maxy, TILE_SIZE, TILE_SIZE)

    try:
        with rasterio.open(cog_path) as src:
            src_nodata = src.nodata
            src_crs = src.crs
            if src_nodata is not None:
                try:
                    if math.isnan(float(src_nodata)):
                        src_nodata = None
                except Exception:  # noqa: BLE001 — nodata غير رقميّ/غير صالح يُتجاهَل بأمان
                    pass

            # سرعة: تخطَّ التصيير إذا لم تتقاطع البلاطة مع حدود الـCOG (بـ3857)
            try:
                from rasterio.warp import transform_bounds

                cb = transform_bounds(src_crs, dst_crs, *src.bounds)
                if cb[2] < minx or cb[0] > maxx or cb[3] < miny or cb[1] > maxy:
                    return None  # لا تقاطع → شفّاف
            except Exception:  # noqa: BLE001 — تعذّر التحقّق → تابع التصيير
                pass

            # قراءة جزئية: لا نقرأ COG كاملاً لكل بلاطة. نعيد الإسقاط مباشرةً من
            # DatasetReader إلى مصفوفة 256×256 كي يستفيد GDAL من tiling/overviews.
            dst = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype="float32")
            reproject(
                source=rasterio.band(src, 1),
                destination=dst,
                src_transform=src.transform,
                src_crs=src_crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.nearest,
                src_nodata=src_nodata,
                dst_nodata=np.nan,
            )
    except Exception:  # noqa: BLE001 — قراءة/إسقاط فشل → fallback شفّاف
        return None

    if not np.isfinite(dst).any():
        return None  # لا بيانات داخل البلاطة → شفّاف

    rgba = colorize(dst, index)
    try:
        return encode_png_rgba(rgba)
    except Exception:  # noqa: BLE001
        return None
