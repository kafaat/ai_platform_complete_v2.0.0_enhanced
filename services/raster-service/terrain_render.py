"""
terrain_render.py — تصيير التضاريس من DEM إلى طبقات خريطة (سدّ فجوة العرض البصريّ).

ثلاث طبقات مستقلّة، لكلٍّ استعمالها (توصية التصميم):
  1) Hillshade — بلاطة Raster رماديّة تُظهر شكل الأرض (مرتفعات/أودية/حواف).
  2) Slope     — بلاطة Raster مُصنّفة بالألوان (0–2/2–5/5–10/10–20/>20٪) — الأهمّ زراعيّاً
                 (اتّجاه الجريان، خطر التعرية، ملاءمة الريّ/الحرث).
  3) Contours  — خطوط Vector (GeoJSON) بقيم الارتفاع — لتخطيط المدرّجات/شبكة الريّ.

⚠ صدق صارم: كلّها تحتاج DEM حقيقيّاً مُهيّأً (``FIELD_DEM_PATH``). لا DEM ⇒ بلاطة شفّافة /
مجموعة فارغة بمظروف ``computed:false`` صريح — لا تلفيق تضاريس. الحساب يتطلّب
numpy/rasterio في التشغيل؛ غيابها ⇒ إبلاغ صادق (None / envelope).

يُعاد استخدام مساعِدات mercator/البلاطة من ``tile_render`` (مصدر واحد للحقيقة الهندسيّة).
"""

from __future__ import annotations

import math

# خريطة ألوان الانحدار (٪ ميل) — 5 فئات زراعيّة. RGBA؛ الشفافيّة تُضبَط للطبقة كاملةً.
# 0–2 مستوٍ · 2–5 خفيف · 5–10 متوسّط · 10–20 شديد · >20 خطر/انجراف.
SLOPE_CLASSES: tuple[tuple[float, tuple[int, int, int], str], ...] = (
    (2.0, (26, 152, 80), "مستوٍ (0–2٪) — ريّ سطحيّ مناسب"),
    (5.0, (166, 217, 106), "خفيف (2–5٪)"),
    (10.0, (254, 224, 139), "متوسّط (5–10٪)"),
    (20.0, (253, 141, 60), "شديد (10–20٪) — يحتاج كنتور/مدرّجات"),
    (float("inf"), (215, 48, 39), "خطر (>20٪) — انجراف؛ حصاد مياه مكثّف"),
)


def slope_legend() -> list[dict]:
    """أسطورة فئات الانحدار (للواجهة) — من مصدر SLOPE_CLASSES نفسه."""
    out: list[dict] = []
    lo = 0.0
    for hi, rgb, label in SLOPE_CLASSES:
        out.append(
            {
                "min_pct": lo,
                "max_pct": None if math.isinf(hi) else hi,
                "color": f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}",
                "label": label,
            }
        )
        lo = hi
    return out


def _dem_mercator_tile(dem_path: str, z: int, x: int, y: int):
    """يُعيد إسقاط نافذة DEM إلى مصفوفة 256×256 في EPSG:3857 لبلاطة (z/x/y).

    يُرجِع ``(elev, ground_px_m)`` — ``elev`` float32 بـNaN خارج البيانات/التغطية،
    و``ground_px_m`` حجم البكسل على الأرض بالأمتار (تصحيح mercator بـcos(lat)).
    ``None`` عند: غياب المكتبات / DEM مفقود / لا تقاطع / فشل الإسقاط (⇒ بلاطة شفّافة).
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.warp import Resampling, reproject, transform_bounds
    except Exception:  # noqa: BLE001 — مكتبات غير متوفّرة ⇒ شفّاف صادق
        return None

    import os

    from tile_render import TILE_SIZE, tile_bounds_3857

    if not dem_path or not os.path.isfile(dem_path):
        return None

    minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)
    dst_crs = "EPSG:3857"
    dst_transform = from_bounds(minx, miny, maxx, maxy, TILE_SIZE, TILE_SIZE)
    try:
        with rasterio.open(dem_path) as src:
            src_nodata = src.nodata
            try:
                cb = transform_bounds(src.crs, dst_crs, *src.bounds)
                if cb[2] < minx or cb[0] > maxx or cb[3] < miny or cb[1] > maxy:
                    return None  # لا تقاطع ⇒ شفّاف
            except Exception:  # noqa: BLE001 — تعذّر الفحص ⇒ تابع
                pass
            dst = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype="float32")
            reproject(
                source=rasterio.band(src, 1),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,  # الارتفاع سلس ⇒ ثنائيّ الخطّيّة أنعم من nearest
                src_nodata=src_nodata,
                dst_nodata=np.nan,
            )
    except Exception:  # noqa: BLE001 — قراءة/إسقاط فشل ⇒ شفّاف صادق
        return None

    if not np.isfinite(dst).any():
        return None

    # حجم البكسل على الأرض: أمتار mercator/256 مضروبة بـcos(lat) (mercator يمطّط بـ1/cos).
    lat_center = 2.0 * math.atan(math.exp(((miny + maxy) / 2.0) / 6378137.0)) - math.pi / 2.0
    merc_px = (maxx - minx) / TILE_SIZE
    ground_px_m = max(merc_px * math.cos(lat_center), 1e-6)
    return dst, ground_px_m


def render_hillshade_tile(
    dem_path: str, z: int, x: int, y: int, azimuth_deg: float = 315.0, altitude_deg: float = 45.0
) -> bytes | None:
    """بلاطة Hillshade رماديّة (PNG) من DEM لبقعة (z/x/y). ``None`` ⇒ شفّاف صادق.

    صيغة ESRI/GDAL القياسيّة (Horn) — إضاءة من الشمال الغربيّ (315°) بارتفاع 45°.
    """
    got = _dem_mercator_tile(dem_path, z, x, y)
    if got is None:
        return None
    import numpy as np
    from tile_render import encode_png_rgba

    elev, px = got
    dzdx = np.gradient(elev, px, axis=1)
    dzdy = np.gradient(elev, px, axis=0)
    slope = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    aspect = np.arctan2(dzdy, -dzdx)
    zenith = math.radians(90.0 - altitude_deg)
    az_math = math.radians((360.0 - azimuth_deg + 90.0) % 360.0)
    hs = np.cos(zenith) * np.cos(slope) + np.sin(zenith) * np.sin(slope) * np.cos(az_math - aspect)
    hs = np.clip(hs, 0.0, 1.0) * 255.0

    valid = np.isfinite(elev) & np.isfinite(hs)
    rgba = np.zeros((elev.shape[0], elev.shape[1], 4), dtype="uint8")
    gray = np.nan_to_num(hs, nan=0.0).astype("uint8")  # NaN خارج البيانات ⇒ 0 (يُخفيه alpha)
    rgba[..., 0] = gray
    rgba[..., 1] = gray
    rgba[..., 2] = gray
    rgba[..., 3] = np.where(valid, 255, 0).astype("uint8")
    return encode_png_rgba(rgba)


def render_slope_tile(dem_path: str, z: int, x: int, y: int) -> bytes | None:
    """بلاطة Slope مُصنّفة بالألوان (PNG) من DEM. ``None`` ⇒ شفّاف صادق.

    الميل ٪ = 100·√((dz/dx)²+(dz/dy)²) بأمتار الأرض (تصحيح cos(lat))؛ يُلوَّن بـSLOPE_CLASSES.
    """
    got = _dem_mercator_tile(dem_path, z, x, y)
    if got is None:
        return None
    import numpy as np
    from tile_render import encode_png_rgba

    elev, px = got
    dzdx = np.gradient(elev, px, axis=1)
    dzdy = np.gradient(elev, px, axis=0)
    slope_pct = 100.0 * np.sqrt(dzdx**2 + dzdy**2)

    valid = np.isfinite(elev) & np.isfinite(slope_pct)
    rgba = np.zeros((elev.shape[0], elev.shape[1], 4), dtype="uint8")
    # تعيين الفئة الأدنى التي يقلّ عنها الميل (تصاعُديّ) — آخر فئة inf تلتقط الباقي.
    assigned = np.zeros(elev.shape, dtype=bool)
    for hi, rgb, _label in SLOPE_CLASSES:
        sel = valid & (~assigned) & (slope_pct < hi if not math.isinf(hi) else True)
        rgba[..., 0][sel] = rgb[0]
        rgba[..., 1][sel] = rgb[1]
        rgba[..., 2][sel] = rgb[2]
        assigned |= sel
    rgba[..., 3] = np.where(valid, 200, 0).astype("uint8")  # شبه-شفّاف فوق الخريطة
    return encode_png_rgba(rgba)


def compute_field_contours(
    dem_path: str | None,
    bbox: list[float] | None = None,
    interval_m: float = 10.0,
    poly: list | None = None,
) -> dict:
    """خطوط كنتور (GeoJSON FeatureCollection) لحقلٍ من DEM مقصوصٍ على مضلّع الحقل (إن
    مُرِّر ``poly``) وإلّا على bbox.

    مربّع مسير (marching squares) نقيّ بـnumpy (بلا اعتماد خارجيّ): لكلّ مستوى ارتفاع
    نُخرِج ``MultiLineString`` بخصائص ``elevation_m``. صدق: لا DEM/bbox أو مكتبات ⇒
    ``features: []`` بمظروف ``computed:false`` + ``source`` — لا كنتور مُلفَّق.
    """
    empty = {"type": "FeatureCollection", "features": [], "computed": False}
    try:
        import numpy as np
        import rasterio
        from rasterio.windows import from_bounds as win_from_bounds
    except Exception:  # noqa: BLE001
        return {**empty, "source": "runtime-libs-missing"}

    import os

    if not dem_path or not os.path.isfile(dem_path):
        return {**empty, "source": "dem-not-configured"}
    if not bbox or len(bbox) != 4:
        return {**empty, "source": "field-bbox-unavailable"}

    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    src_crs = None
    try:
        with rasterio.open(dem_path) as src:
            src_crs = src.crs
            b = (min_lon, min_lat, max_lon, max_lat)
            # صحّة CRS: أعِد إسقاط bbox (lon/lat) إلى src.crs قبل النافذة إن كان المصدر
            # مُسقَطاً (UTM…) وإلّا نافذة خاطئة على raster غير جغرافيّ.
            if src_crs is not None and src_crs.to_epsg() != 4326:
                from rasterio.warp import transform_bounds

                b = transform_bounds("EPSG:4326", src_crs, *b)
            window = win_from_bounds(*b, transform=src.transform)
            dem = src.read(1, window=window, masked=True).filled(np.nan).astype("float32")
            wtransform = src.window_transform(window)
            if poly:  # قصّ على مضلّع الحقل (لا كنتور خارج الحدّ)
                from tile_render import mask_array_by_polygon

                dem = mask_array_by_polygon(dem, wtransform, src_crs, poly)
    except Exception:  # noqa: BLE001
        return {**empty, "source": "dem-read-failed"}

    if dem.size == 0 or not np.isfinite(dem).any():
        return {**empty, "source": "field-outside-dem"}

    ev = dem[np.isfinite(dem)]
    lo = math.floor(float(ev.min()) / interval_m) * interval_m
    hi = float(ev.max())
    levels = []
    lv = lo
    while lv <= hi and len(levels) < 200:  # حدّ أمان
        if lv >= ev.min():
            levels.append(lv)
        lv += interval_m

    rows, cols = dem.shape

    # عند DEM مُسقَط، wtransform يُخرج إحداثيّات المصدر (أمتار) لا lon/lat — أعِد إسقاطها
    # إلى EPSG:4326 كي يبقى GeoJSON بإحداثيّات جغرافيّة (DEM جغرافيّ ⇒ لا تحويل، لا كلفة).
    _reproj = None
    if src_crs is not None and src_crs.to_epsg() != 4326:
        from rasterio.warp import transform as _warp_transform

        def _reproj(x, y):
            xs, ys = _warp_transform(src_crs, "EPSG:4326", [x], [y])
            return xs[0], ys[0]

    def _pt(col_f: float, row_f: float) -> list[float]:
        # (col,row) شبه-مستمرّ ⇒ إحداثيّات النافذة (مركز البكسل +0.5) ثمّ lon/lat.
        x, y = wtransform * (col_f + 0.5, row_f + 0.5)
        if _reproj is not None:
            x, y = _reproj(x, y)
        return [round(x, 7), round(y, 7)]

    features = []
    for level in levels:
        segments: list[list[list[float]]] = []
        # مربّع مسير: لكلّ خليّة 2×2، تقاطعات الحوافّ حيث يعبر المستوى.
        for r in range(rows - 1):
            for c in range(cols - 1):
                tl, tr = dem[r, c], dem[r, c + 1]
                bl, br = dem[r + 1, c], dem[r + 1, c + 1]
                if not (
                    np.isfinite(tl) and np.isfinite(tr) and np.isfinite(bl) and np.isfinite(br)
                ):
                    continue

                def _cross(v1, v2, cc1, rr1, cc2, rr2, lvl=level):
                    if (v1 < lvl) == (v2 < lvl):
                        return None
                    t = (lvl - v1) / (v2 - v1) if v2 != v1 else 0.5
                    return [cc1 + (cc2 - cc1) * t, rr1 + (rr2 - rr1) * t]

                pts = []
                top = _cross(tl, tr, c, r, c + 1, r)
                right = _cross(tr, br, c + 1, r, c + 1, r + 1)
                bottom = _cross(bl, br, c, r + 1, c + 1, r + 1)
                left = _cross(tl, bl, c, r, c, r + 1)
                for e in (top, right, bottom, left):
                    if e is not None:
                        pts.append(e)
                # حالة قياسيّة: تقاطعان ⇒ قطعة واحدة. (السرج بأربعة يُخرَج قطعتين تباعاً.)
                if len(pts) == 2:
                    segments.append([_pt(*pts[0]), _pt(*pts[1])])
                elif len(pts) == 4:
                    segments.append([_pt(*pts[0]), _pt(*pts[1])])
                    segments.append([_pt(*pts[2]), _pt(*pts[3])])
        if segments:
            features.append(
                {
                    "type": "Feature",
                    "properties": {"elevation_m": round(level, 1)},
                    "geometry": {"type": "MultiLineString", "coordinates": segments},
                }
            )

    return {
        "type": "FeatureCollection",
        "features": features,
        "computed": True,
        "source": "dem",
        "interval_m": interval_m,
        "levels": len(levels),
    }
