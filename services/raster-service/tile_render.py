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

# سقف افتراضيّ لأبعاد نافذة القراءة (بكسل/محور): يمنع تحميل نافذة ضخمة (ذاكرة/زمن) عند
# bbox كبير أو raster عالي الدقّة — يُخفَّض بالعيّنة عند القراءة عبر out_shape.
MAX_READ_DIM = int(__import__("os").getenv("RASTER_MAX_READ_DIM", "2048"))


def read_field_window(src, lonlat_bbox, *, max_dim: int = MAX_READ_DIM):
    """يقرأ نافذة الحقل من raster مفتوح مع **تصحيح CRS** و**سقف حجم** — مسار القراءة
    الموحَّد لكلّ الإحصاءات المتجهيّة (تضاريس/تربة/مناطق).

    - يُعيد إسقاط ``lonlat_bbox`` (EPSG:4326) إلى ``src.crs`` قبل ``from_bounds`` حين لا
      يكون المصدر بـEPSG:4326 (وإلّا نافذة خاطئة على raster مُسقَط: UTM/Homolosine…).
    - يسقف أبعاد القراءة عند ``max_dim`` (تخفيض عيّنة عند القراءة) لتفادي نافذة ضخمة.
    - يُعيد ``(arr, scale_x, scale_y)``: arr float32 بـ``NaN`` للـnodata، وscale = أبعاد
      النافذة ÷ أبعاد المخرَج (عامل التخفيض؛ 1.0 بلا تخفيض) كي يضبط المُستدعي حجم البكسل.
      يُعيد ``None`` عند فشل القراءة أو نافذة فارغة (لا تلفيق).
    """
    import numpy as np
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    minx, miny, maxx, maxy = (float(v) for v in lonlat_bbox)
    if src.crs is not None:
        try:
            if src.crs.to_epsg() != 4326:  # None (CRS بلا رمز EPSG مثل Homolosine) ⇒ يُعاد إسقاطه
                minx, miny, maxx, maxy = transform_bounds(
                    "EPSG:4326", src.crs, minx, miny, maxx, maxy
                )
        except Exception:  # noqa: BLE001 — فشل الإسقاط ⇒ استعمل الحدود كما هي (احتياطيّ)
            pass
    try:
        window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        win_w, win_h = float(window.width), float(window.height)
        if win_w <= 0 or win_h <= 0:
            return None
        if win_w <= max_dim and win_h <= max_dim:
            arr = src.read(1, window=window, masked=True).filled(np.nan).astype("float32")
            return arr, 1.0, 1.0
        out_w = int(min(max_dim, math.ceil(win_w)))
        out_h = int(min(max_dim, math.ceil(win_h)))
        arr = (
            src.read(1, window=window, out_shape=(out_h, out_w), masked=True)
            .filled(np.nan)
            .astype("float32")
        )
        return arr, win_w / out_w, win_h / out_h
    except Exception:  # noqa: BLE001
        return None


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
    # مؤشّرات مُضافة للقائمة المنسدلة (نطاقات دقيقة بدل الافتراضيّ NDVI):
    "savi": (-0.2, 0.9, False),  # غطاء مُعدَّل للتربة — مثل NDVI
    "gndvi": (-0.2, 0.9, False),  # غطاء أخضر — مثل NDVI
    "msi": (0.4, 1.6, True),  # إجهاد مائيّ B11/B08: عالٍ = إجهاد (أحمر) ⇒ نعكس
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


def _reproject_dataset_mask(src, *, dst_transform, dst_crs: str, out_shape: tuple[int, int]):
    """Reproject GDAL internal/per-dataset mask to the render grid.

    Some GeoTIFFs contain finite values outside the AOI (for example 0.0) plus a
    valid mask band. Passing only ``src_nodata`` to ``reproject`` can make GDAL
    ignore the mask band, producing opaque dark stripes in tiles/thumbnails.
    Reproject the mask explicitly and apply it after the value warp.
    """
    try:
        import numpy as np
        from rasterio.warp import Resampling, reproject

        src_mask = src.read_masks(1)
        dst_mask = np.zeros(out_shape, dtype="uint8")
        reproject(
            source=src_mask,
            destination=dst_mask,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
            src_nodata=0,
            dst_nodata=0,
        )
        return dst_mask
    except Exception:  # noqa: BLE001 — mask absence/warp issue must not break rendering
        return None


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
            dst_mask = _reproject_dataset_mask(
                src,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                out_shape=(TILE_SIZE, TILE_SIZE),
            )
            if dst_mask is not None:
                dst[dst_mask == 0] = np.nan
    except Exception:  # noqa: BLE001 — قراءة/إسقاط فشل → fallback شفّاف
        return None

    if not np.isfinite(dst).any():
        return None  # لا بيانات داخل البلاطة → شفّاف

    rgba = colorize(dst, index)
    try:
        return encode_png_rgba(rgba)
    except Exception:  # noqa: BLE001
        return None


def render_cog_thumbnail_png(cog_path: str, index: str, max_px: int = 160) -> bytes | None:
    """يصيّر **مُصغَّرة** كاملة للحقل من COG مقصوص (لا بلاطة XYZ) — لشريط السجلّ الزمنيّ.

    يعيد إسقاط امتداد الـCOG كلّه (وهو أصلاً مقصوص على bbox الحقل + مُقنَّع بالمضلّع)
    إلى صورة صغيرة (أطول ضلع = ``max_px``) محافظاً على نسبة الأبعاد، ثمّ يلوّن بتدرّج
    المؤشّر ويرمّز PNG. خارج المضلّع (NaN) → شفّاف، فتظهر صورة شكل الحقل وحده.

    None عند: غياب rasterio / ملفّ مفقود / لا بيانات صالحة (مشهد مُقنَّع كلّيّاً).
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.warp import Resampling, reproject, transform_bounds
    except Exception:  # noqa: BLE001 — rasterio غير متوفّر → لا مُصغَّرة
        return None

    try:
        with rasterio.open(cog_path) as src:
            src_nodata = src.nodata
            if src_nodata is not None:
                try:
                    if math.isnan(float(src_nodata)):
                        src_nodata = None
                except Exception:  # noqa: BLE001
                    pass
            # امتداد الـCOG في 3857 (مصدره غالباً UTM) — هو امتداد الحقل المقصوص.
            minx, miny, maxx, maxy = transform_bounds(
                "EPSG:4326" if not src.crs else src.crs, "EPSG:3857", *src.bounds
            )
            span_x = max(1e-6, maxx - minx)
            span_y = max(1e-6, maxy - miny)
            # حجم الخرج بنسبة أبعاد الحقل، أطول ضلع = max_px (الأصغر ≥ 16px).
            if span_x >= span_y:
                out_w = max_px
                out_h = max(16, int(round(max_px * span_y / span_x)))
            else:
                out_h = max_px
                out_w = max(16, int(round(max_px * span_x / span_y)))
            dst_transform = from_bounds(minx, miny, maxx, maxy, out_w, out_h)
            dst = np.full((out_h, out_w), np.nan, dtype="float32")
            reproject(
                source=rasterio.band(src, 1),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs="EPSG:3857",
                resampling=Resampling.nearest,
                src_nodata=src_nodata,
                dst_nodata=np.nan,
            )
            dst_mask = _reproject_dataset_mask(
                src,
                dst_transform=dst_transform,
                dst_crs="EPSG:3857",
                out_shape=(out_h, out_w),
            )
            if dst_mask is not None:
                dst[dst_mask == 0] = np.nan
    except Exception:  # noqa: BLE001 — قراءة/إسقاط فشل → لا مُصغَّرة
        return None

    if not np.isfinite(dst).any():
        return None  # لا بيانات صالحة (غيوم/خارج المضلّع) → لا مُصغَّرة

    rgba = colorize(dst, index)
    try:
        return encode_png_rgba(rgba)
    except Exception:  # noqa: BLE001
        return None


def apply_polygon_mask(cog_path: str, geom_4326: dict) -> None:
    """يطبّق قناع مضلّع **بكسليّ دقيق** على COG في مكانه: خارج المضلّع → NaN.

    ``geom_4326``: GeoJSON (Polygon/MultiPolygon) بـEPSG:4326. يُعاد إسقاطه إلى CRS
    الراستر ثمّ ``rasterio.mask`` يملأ الخارج بـNaN (nodata) — قصّ مستقلّ عن قصّ
    المزوّد (Sentinel Hub) ومطابق لحافّة الحقل (مصدر الحقيقة للقصّ). يُعيد الكتابة في
    نفس الملفّ. يرفع عند الفشل (لا rasterio/هندسة لا تتقاطع) فيعالجه المُستدعي.

    (إعادة دمج توحيد main↔cert: ميزة قصّ CDSE poly من main فوق tile_render الخاصّ بـcert.)"""
    import rasterio
    from rasterio.mask import mask as _rio_mask
    from rasterio.warp import transform_geom

    with rasterio.open(cog_path) as src:
        geom_src = transform_geom("EPSG:4326", src.crs, geom_4326)
        out_img, _ = _rio_mask(src, [geom_src], crop=False, nodata=float("nan"), filled=True)
        profile = src.profile.copy()
    profile.update(nodata=float("nan"))
    with rasterio.open(cog_path, "w", **profile) as dst:
        dst.write(out_img)
