"""
terrain_analysis.py — تحليل التضاريس من DEM (سدّ فجوة: لا انحدار/صرف).

المراجعات أشارت لغياب DEM. الآن مع Copernicus DEM (30م)، تحسب هذه الوحدة:
الانحدار (slope) والاتّجاه (aspect) من نموذج الارتفاع — أساس تخطيط حصاد
المياه، اتّجاه الجريان، ومواقع السدود الترابيّة في زراعة اليمن المُدرّجة.

⚠ الحساب الفعلي يتطلّب numpy/rasterio في بيئة التشغيل. هنا منطق الانحدار
(صحيح رياضيّاً) + إبلاغ صادق عند غياب المكتبات.
"""

from __future__ import annotations

import math
import os


def _finite_ring(raw) -> list[list[float]] | None:
    """حلقة GeoJSON صالحة ⇒ ``[[lon,lat]…]``؛ شاذّة ⇒ ``None`` (لا اختزال صامت).

    صالحة = ٤ إحداثيّات على الأقلّ (حلقة GeoJSON المغلقة الدنيا: مثلّث + إغلاق) وكلّ
    إحداثيّة رقمان منتهيان. نقطة ناقصة/غير رقميّة/NaN/Inf تُسقِط الحلقة كلّها لا النقطة
    وحدها — إسقاط نقطة بصمت يغيّر شكل الحقل ثمّ يُحسَب كأنّه الحقل.
    """
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    ring: list[list[float]] = []
    for p in raw:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        try:
            lon, lat = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(lon) and math.isfinite(lat)):
            return None
        ring.append([lon, lat])
    return ring


def _field_polygons(geom: dict | None) -> list[list[list[list[float]]]] | None:
    """أجزاء الحقل ``[[خارجيّة, ثقب…], …]`` لكلّ أجزاء Polygon/MultiPolygon، أو ``None``.

    تُحفَظ الحلقات الداخليّة (الثقوب): إسقاطها كان يعدّ الثقب مساحةَ حقل. أيّ حلقة شاذّة
    (خارجيّة أو داخليّة) أو جزء فارغ ⇒ ``None`` للهندسة كلّها — رفض لا اختزال.
    """
    if not isinstance(geom, dict):
        return None
    g = geom.get("geometry") if geom.get("type") == "Feature" else geom
    if not isinstance(g, dict):
        return None
    coords = g.get("coordinates")
    if g.get("type") == "Polygon":
        raw_parts = [coords]
    elif g.get("type") == "MultiPolygon":
        raw_parts = coords
    else:
        return None
    if not isinstance(raw_parts, (list, tuple)) or not raw_parts:
        return None
    polygons: list[list[list[list[float]]]] = []
    for part in raw_parts:
        if not isinstance(part, (list, tuple)) or not part:
            return None
        rings = [_finite_ring(r) for r in part]
        if any(r is None for r in rings):
            return None
        polygons.append(rings)  # type: ignore[arg-type]
    return polygons


def field_terrain_extent(geom: dict | None) -> tuple[list[float] | None, list | None]:
    """يستخرج (bbox, الحدّ) من GeoJSON حقل — للقصّ الدقيق على المضلّع.

    يدعم Polygon/MultiPolygon/Feature. شكل الحدّ (يفهمه ``tile_render.mask_array_by_polygon``):
      • بلا ثقوب: حلقة خارجيّة واحدة ``[[lon,lat]…]`` لجزء واحد، أو **قائمة الحلقات الخارجيّة
        لكلّ الأجزاء** لـMultiPolygon متعدّد الأجزاء (الشكلان الموروثان كما هما).
      • بثقب واحد على الأقلّ: **قائمة مضلّعات** ``[[خارجيّة, ثقب…], …]`` (حتّى لجزء واحد، كي لا
        يلتبس الثقب بجزءٍ ثانٍ) فيُقنَّع الثقب خارج الحقل لا داخله.
    الـbbox يُحسَب على **كلّ** الحلقات الخارجيّة لكلّ الأجزاء. صدق: هندسة غائبة/شاذّة (حلقة دون
    ٤ إحداثيّات، إحداثيّة غير منتهية، جزء فارغ) ⇒ ``(None, None)`` فيُرجِع الحساب
    ``computed=false`` — لا نختزلها بصمت ولا نلفّق مربّعاً إقليميّاً.
    """
    polygons = _field_polygons(geom)
    if not polygons:
        return None, None
    lons = [p[0] for poly in polygons for p in poly[0]]
    lats = [p[1] for poly in polygons for p in poly[0]]
    bbox = [min(lons), min(lats), max(lons), max(lats)]
    if any(len(poly) > 1 for poly in polygons):
        return bbox, polygons
    exteriors = [poly[0] for poly in polygons]
    return bbox, (exteriors[0] if len(exteriors) == 1 else exteriors)


def _boundary_is_valid(poly) -> bool:
    """يتحقّق من حدٍّ بأيّ شكل يقبله ``mask_array_by_polygon`` (حلقة/حلقات/مضلّعات)."""
    depth = 0
    node = poly
    while isinstance(node, (list, tuple)) and node:
        depth += 1
        node = node[0]
    if depth == 2:
        polygons = [[poly]]
    elif depth == 3:
        polygons = [[ring] for ring in poly]
    elif depth == 4:
        polygons = poly
    else:
        return False
    return all(
        isinstance(part, (list, tuple)) and part and all(_finite_ring(r) is not None for r in part)
        for part in polygons
    )


def _no_gradient_support_envelope() -> dict:
    """رفض صريح حين لا يدعم الـDEM تدرّجاً: محور دون خليّتين (``np.gradient`` يرفع)، أو لا
    خليّة انحدار منتهية (كلّ جار NaN). كان الفرع يُرجِع ``computed: True`` بانحدار 0.0 —
    أي «أرض مستوية» مُخترَعة تُغذّي توصية الريّ السطحيّ. الانحدار الصفريّ **المَقيس** على أرض
    مستوية يبقى ``computed: True``؛ هذا الرفض لغياب القياس لا لقيمته."""
    return {
        "computed": False,
        "source": "dem-insufficient-gradient-support",
        "reason": (
            "نافذة الارتفاع لا تكفي لحساب الانحدار: يلزم خليّتان متجاورتان صالحتان على كلّ "
            "محور — لا يُعرَض انحدار صفريّ لم يُقَس"
        ),
    }


def compute_slope_aspect(dem_path: str, pixel_size_m: float = 30.0) -> dict:
    """يحسب الانحدار (درجات) والاتّجاه من DEM عبر طريقة Horn (المعياريّة).

    Horn: تدرّج بـ3×3 نافذة (ArcGIS/GDAL يستخدمانها). يُرجِع إحصاءات الانحدار
    لتخطيط حصاد المياه. صدق: يكتب فعليّاً عند توفّر rasterio؛ وإلّا يُبلّغ.
    """
    try:
        import numpy as np
        import rasterio
    except ImportError:
        return {"computed": False, "reason": "numpy/rasterio غير متوفّر — يُحسب في التشغيل"}

    # صدق: DEM مفقود/غير مقروء ⇒ مظروف «غير محسوب» صريح لا استثناء (تدقيق 2026-07-05).
    # الـdocstring يعِد بـ«يُبلّغ»؛ فتح ملفّ مفقود مباشرةً كان يرفع RasterioIOError.
    if not dem_path or not os.path.isfile(dem_path):
        return {"computed": False, "reason": f"مصدر DEM غير موجود: {dem_path or '—'}"}
    try:
        with rasterio.open(dem_path) as src:
            # masked=True يحترم nodata من بيانات DEM الوصفيّة (مثل -32768/-9999): بدونه
            # يُعامَل الحارس كارتفاعٍ حقيقيّ (isfinite لا يمسكه) فيفسد الإحصاء ويخترع تدرّجاً.
            dem = src.read(1, masked=True).astype("float32").filled(np.nan)
    except rasterio.errors.RasterioIOError as e:
        return {"computed": False, "reason": f"تعذّر قراءة DEM: {type(e).__name__}"}

    if dem.ndim != 2 or min(dem.shape) < 2:
        return _no_gradient_support_envelope()
    # تدرّج Horn (3×3) — dz/dx و dz/dy
    dzdx = np.gradient(dem, pixel_size_m, axis=1)
    dzdy = np.gradient(dem, pixel_size_m, axis=0)
    slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    slope_deg = np.degrees(slope_rad)
    aspect = np.degrees(np.arctan2(dzdy, -dzdx))
    aspect = np.where(
        aspect < 0, 90.0 - aspect, np.where(aspect > 90.0, 360.0 - aspect + 90.0, 90.0 - aspect)
    )

    sv = slope_deg[np.isfinite(slope_deg)]
    if not sv.size:
        return _no_gradient_support_envelope()
    return {
        "computed": True,
        "slope_deg": {
            "min": float(np.min(sv)),
            "max": float(np.max(sv)),
            "mean": float(np.mean(sv)),
        },
        "flat_pct": float((sv < 2).sum() / sv.size * 100),
        "steep_pct": float((sv > 15).sum() / sv.size * 100),
        "note": "الانحدار<2° مناسب للريّ السطحي؛ >15° يحتاج مدرّجات/حصاد مياه",
    }


def compute_field_terrain(
    dem_path: str | None,
    bbox: list[float] | None = None,
    pixel_size_m: float = 30.0,
    poly: list | None = None,
) -> dict:
    """يحسب إحصاءات تضاريس حقل (ارتفاع + انحدار/اتّجاه) من DEM مقصوصٍ على bbox الحقل.

    الأساس الصادق لعرض التضاريس: يقصّ نموذج الارتفاع على مربّع إحاطة الحقل
    (lon/lat, EPSG:4326) ثمّ يحسب إحصاءات الارتفاع والانحدار عبر Horn. لا تلفيق:
      • لا DEM مُهيّأ/موجود ⇒ ``{computed: false, source: 'dem-not-configured'}``.
      • لا bbox للحقل ⇒ ``{computed: false, source: 'field-bbox-unavailable'}`` (لا
        نحسب إحصاءات إقليميّة ونلصقها بالحقل).
      • numpy/rasterio غير متوفّرة ⇒ يُبلّغ (تُحسب في التشغيل).
    """
    try:
        import numpy as np
        import rasterio
        from tile_render import read_field_window
    except ImportError:
        return {
            "computed": False,
            "source": "runtime-libs-missing",
            "reason": "numpy/rasterio غير متوفّر — يُحسب في التشغيل",
        }

    if not dem_path or not os.path.isfile(dem_path):
        return {
            "computed": False,
            "source": "dem-not-configured",
            "reason": f"مصدر DEM غير مُهيّأ/موجود: {dem_path or '—'}",
        }
    if not bbox or len(bbox) != 4:
        return {
            "computed": False,
            "source": "field-bbox-unavailable",
            "reason": "مربّع إحاطة الحقل غير متاح — لا نحسب تضاريس إقليميّة كأنّها للحقل",
        }
    if poly is not None and not _boundary_is_valid(poly):
        # حدّ شاذّ (حلقة دون ٤ إحداثيّات/إحداثيّة غير منتهية) ⇒ رفض لا قصّ مُختزَل: القناع
        # كان يُسقِط الحلقة الشاذّة بصمت فيُحسَب الحقل بلا قصّ (أو بلا ثقبه) كأنّه الحقل.
        return {
            "computed": False,
            "source": "field-geometry-invalid",
            "reason": "حدّ الحقل غير صالح (حلقة دون ٤ إحداثيّات أو إحداثيّة غير منتهية)",
        }

    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    # قيمة ابتدائيّة فقط. لم تعد «احتياطيّاً عند تعذّر الاشتقاق»: تعذّر اشتقاق الدقّة
    # صار يُرجِع computed=False (dem-resolution-unavailable) بدل المضيّ بانحدار خاطئ.
    px_x_m = px_y_m = float(pixel_size_m)
    try:
        with rasterio.open(dem_path) as src:
            # قراءة موحَّدة: تصحيح CRS (bbox lon/lat ⇒ src.crs قبل النافذة) + سقف حجم.
            # masked=True يحترم nodata (‑32768/‑9999…): بدونه يُحسَب الحارس كارتفاع حقيقيّ
            # فيفسد min/max/mean ويخترع تدرّجاً هائلاً عند حوافّ الفجوات ⇒ انحدار خاطئ.
            read = read_field_window(src, (min_lon, min_lat, max_lon, max_lat), poly_lonlat=poly)
            if read is None:
                return {
                    "computed": False,
                    "source": "field-outside-dem",
                    "reason": "الحقل خارج تغطية DEM أو نافذة فارغة",
                }
            dem, scale_x, scale_y = read
            # صحّة CRS: لا نحسب الانحدار من درجات lat/lon مباشرة. حجم البكسل على الأرض
            # بالأمتار لكلّ محور: DEM مُسقَط (أمتار) ⇒ src.res مباشرةً؛ DEM جغرافيّ (درجات)
            # ⇒ y = res·111320، x = res·111320·cos(lat) (البكسل الأفقيّ أقصر بـcos(lat)).
            # scale_* يضبط الحجم عند تخفيض العيّنة (نافذة كبيرة): البكسل الأرضيّ يكبر بالعامل.
            try:
                xres, yres = (abs(v) for v in src.res)
                if src.crs and src.crs.is_geographic:
                    lat_c = math.radians((min_lat + max_lat) / 2.0)
                    px_x_m = xres * 111320.0 * math.cos(lat_c) * scale_x
                    px_y_m = yres * 111320.0 * scale_y
                else:
                    px_x_m, px_y_m = xres * scale_x, yres * scale_y
            except (TypeError, ValueError, AttributeError) as e:
                # SILENT-EXCEPTION-HANDLERS-11-01 — أخطر المواضع الأحد عشر: هذا الفرع
                # هو **تصحيح CRS** الذي يقول التعليق أعلاه إنّه إلزاميّ («لا نحسب
                # الانحدار من درجات lat/lon مباشرة»). وابتلاعه كان يُسقِط الحساب إلى
                # `pixel_size_m` القادم من المُستدعي، ثمّ يمضي فيُرجِع `computed: True`
                # بانحدار **خاطئ يبدو معقولاً**.
                #
                # وهذا يناقض عقد الدالّة نفسها: كلّ إخفاق شقيق (runtime-libs-missing ·
                # dem-not-configured · field-bbox-unavailable · field-outside-dem ·
                # dem-read-failed) يُرجِع `computed: False` بسبب صريح. هذا المسار وحده
                # كان يُرجِع جواباً خاطئاً بزيّ جواب صحيح — تناقض عقد لا قرار منتج.
                #
                # fail-closed: لا رقم أفضل من رقم كاذب. و`AttributeError` تبقى ملتقَطة
                # عمداً (غياب `src.res`/`src.crs` عطب بنيويّ في الـDEM) لكنّها تُصنَّف
                # الآن صراحةً بدل أن تتحوّل انحداراً مخترَعاً.
                return {
                    "computed": False,
                    "source": "dem-resolution-unavailable",
                    "reason": (
                        "تعذّر اشتقاق دقّة البكسل الأرضيّة من الـDEM "
                        f"({type(e).__name__}) — لا يُحسَب انحدار بدقّة غير مُثبَتة"
                    ),
                }
    except rasterio.errors.RasterioIOError as e:
        return {
            "computed": False,
            "source": "dem-read-failed",
            "reason": f"تعذّر قراءة DEM: {type(e).__name__}",
        }

    if dem.size == 0:
        return {
            "computed": False,
            "source": "field-outside-dem",
            "reason": "مربّع إحاطة الحقل خارج تغطية DEM",
        }

    finite = np.isfinite(dem)
    ev = dem[finite]
    if not ev.size:
        return {
            "computed": False,
            "source": "dem-no-valid-pixels",
            "reason": "لا توجد قياسات ارتفاع صالحة داخل نطاق الحقل",
        }
    if dem.ndim != 2 or min(dem.shape) < 2:
        return _no_gradient_support_envelope()
    dzdx = np.gradient(dem, max(px_x_m, 1e-6), axis=1)
    dzdy = np.gradient(dem, max(px_y_m, 1e-6), axis=0)
    slope_deg = np.degrees(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))
    aspect = np.degrees(np.arctan2(dzdy, -dzdx))
    aspect = np.where(
        aspect < 0, 90.0 - aspect, np.where(aspect > 90.0, 360.0 - aspect + 90.0, 90.0 - aspect)
    )
    sv = slope_deg[np.isfinite(slope_deg)]
    if not sv.size:
        # ارتفاعات صالحة لكن معزولة (لا جار صالح على أحد المحورين) ⇒ لا انحدار مَقيس.
        return _no_gradient_support_envelope()

    # الاتّجاه الغالب (8 جهات) للجريان السطحيّ.
    dirs = ["شمال", "شمال شرق", "شرق", "جنوب شرق", "جنوب", "جنوب غرب", "غرب", "شمال غرب"]
    av = aspect[np.isfinite(aspect)]
    dominant_aspect = None
    if av.size:
        # متوسّط دائريّ (الاتّجاه كمّيّة زاويّة): المتوسّط الخطّيّ لزوايا حول 0/360 يعطي
        # عكس الاتّجاه (350° و10° ⇒ خطّيّ=180°=جنوب، والصحيح=0°=شمال). atan2(mean sin, mean cos).
        ar = np.radians(av)
        mean_ang = np.degrees(np.arctan2(np.mean(np.sin(ar)), np.mean(np.cos(ar)))) % 360
        idx = int((mean_ang + 22.5) // 45) % 8
        dominant_aspect = dirs[idx]

    return {
        "computed": True,
        "source": "dem",
        "elevation_m": {
            "min": float(np.min(ev)) if ev.size else None,
            "max": float(np.max(ev)) if ev.size else None,
            "mean": float(np.mean(ev)) if ev.size else None,
        },
        "slope_deg": {
            "min": float(np.min(sv)),
            "max": float(np.max(sv)),
            "mean": float(np.mean(sv)),
        },
        "flat_pct": float((sv < 2).sum() / sv.size * 100),
        "steep_pct": float((sv > 15).sum() / sv.size * 100),
        "dominant_aspect": dominant_aspect,
        "note": "الانحدار<2° مناسب للريّ السطحي؛ >15° يحتاج مدرّجات/حصاد مياه",
    }


def classify_water_harvesting(slope_deg_mean: float) -> dict:
    """يصنّف ملاءمة حصاد المياه حسب الانحدار (إرشادي زراعي).

    صدق: عتبات إرشاديّة من أدبيّات حصاد المياه؛ القرار النهائي ميداني.
    """
    if slope_deg_mean < 2:
        technique = "أحواض مستوية (basin) — انحدار منخفض"
        suitability = "ممتاز للريّ السطحي"
    elif slope_deg_mean < 8:
        technique = "مصاطب كنتوريّة (contour) + خطوط جريان"
        suitability = "جيّد لحصاد المياه الكنتوري"
    elif slope_deg_mean < 15:
        technique = "مدرّجات (terraces) — تقليديّ يمني"
        suitability = "يحتاج مدرّجات لمنع الانجراف"
    else:
        technique = "مدرّجات حجريّة + سدود ترابيّة صغيرة"
        suitability = "حادّ — حصاد مياه مكثّف ضروري"
    return {
        "slope_deg_mean": round(slope_deg_mean, 1),
        "recommended_technique": technique,
        "suitability": suitability,
        "note": "إرشادي من أدبيّات حصاد المياه — تحقّق ميداني مطلوب",
    }


def interpret_terrain_for_agronomy(terrain: dict) -> dict | None:
    """يربط إحصاءات التضاريس بقرارات زراعيّة إرشاديّة (خطر تعرية/سيولة/إجراءات).

    من إحصاء ``compute_field_terrain`` المحسوب (slope_deg + dominant_aspect). لا يُنتِج
    شيئاً إن لم يُحسَب التضاريس (``computed:false``) — لا تلفيق قرار بلا بيانات. العتبات
    من أدبيّات تعرية التربة/ملاءمة الآليّات (٪ ميل)؛ القرار النهائيّ ميدانيّ (إرشاديّ).
    """
    if not terrain or not terrain.get("computed"):
        return None
    mean_deg = float((terrain.get("slope_deg") or {}).get("mean") or 0.0)
    max_deg = float((terrain.get("slope_deg") or {}).get("max") or 0.0)
    mean_pct = round(math.tan(math.radians(mean_deg)) * 100.0, 1)
    max_pct = round(math.tan(math.radians(max_deg)) * 100.0, 1)
    aspect = terrain.get("dominant_aspect")

    # خطر التعرية (٪ ميل — عتبات أدبيّات حفظ التربة).
    if mean_pct < 2:
        erosion = "very_low"
    elif mean_pct < 5:
        erosion = "low"
    elif mean_pct < 10:
        erosion = "medium"
    elif mean_pct < 15:
        erosion = "high"
    else:
        erosion = "severe"

    # ملاءمة مرور الآليّات (الحرث/الحصاد): ميل عالٍ ⇒ خطر انقلاب/انزلاق.
    if mean_pct < 8:
        traffic = "low"
    elif mean_pct < 15:
        traffic = "medium"
    else:
        traffic = "high"

    actions: list[str] = []
    if mean_pct >= 5:
        actions.append("فضّل الريّ الكنتوريّ/بالتنقيط على الغمر السطحيّ (ينجرف على المنحدر).")
    if mean_pct >= 10:
        actions.append("أنشئ مصاطب/خطوط كنتور لكسر طول المنحدر وتقليل التعرية.")
    if max_pct >= 20:
        actions.append("ضع نقاط عيّنات تربة إضافيّة في مناطق الميل الأعلى (تربة أرقّ محتملة).")
    if traffic == "high":
        actions.append("قيّد مرور الآليّات الثقيلة في المناطق الحادّة (خطر انزلاق/انضغاط).")
    if aspect in ("جنوب", "جنوب غرب", "جنوب شرق"):
        actions.append("الجهات الجنوبيّة أكثر تبخّراً — راجع جدولة الريّ فيها.")
    if not actions:
        actions.append("التضاريس شبه مستوية — لا قيود انحدار خاصّة؛ تابع الممارسة المعتادة.")

    return {
        "mean_slope_pct": mean_pct,
        "max_slope_pct": max_pct,
        "dominant_aspect": aspect,
        "erosion_risk": erosion,
        "trafficability_risk": traffic,
        "recommended_actions": actions,
        "note": "إرشاديّ من أدبيّات حفظ التربة/ملاءمة الآليّات — لا يُغني عن الفحص الميدانيّ.",
    }
