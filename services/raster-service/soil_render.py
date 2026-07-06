"""
soil_render.py — طبقة تربة بصريّة (SoilGrids/ISRIC) كبلاطات Raster فوق الحقل.

توجيه اختيار عيّنات المختبر (لا بديل عنه): تُعرَض خصائص التربة كبلاطات ملوّنة شفّافة
لتقسيم الحقل بصريّاً واختيار مواقع العيّنات. **تحذير إلزاميّ**: SoilGrids تقديريّ عالميّ
بدقّة ~250م — لا يكفي وحده لحقل 1–2 هكتار، ولا يُغني عن التحليل المختبريّ.

صدق صارم: يحتاج مصدر SoilGrids raster مُهيّأً (``SOILGRIDS_DIR`` — مجلّد GeoTIFF لكلّ
(خاصّيّة، عمق) مثل ``phh2o_0-30cm.tif``). بلا مصدر ⇒ بلاطة شفّافة + ``available:false``
+ سبب — لا تلفيق خصائص تربة. الحساب يتطلّب numpy/rasterio؛ غيابها ⇒ إبلاغ صادق.

مصادر: ISRIC SoilGrids 2.0 (CC-BY 4.0). معاملات التحويل «الوحدة المُخزّنة → التقليديّة»
من توثيق SoilGrids الرسميّ (لا اختلاق وحدات).
"""

from __future__ import annotations

import os

# الأعماق القياسيّة الستّة في SoilGrids 2.0.
# الأعماق: الستّة المعياريّة في SoilGrids 2.0 + عمق مُجمَّع شائع (0-30cm) إن زُوِّد.
SOIL_DEPTHS: tuple[str, ...] = (
    "0-5cm",
    "5-15cm",
    "15-30cm",
    "0-30cm",
    "30-60cm",
    "60-100cm",
    "100-200cm",
)

# لكلّ خاصّيّة: (الاسم، الوحدة التقليديّة، معامل القسمة للتحويل من المُخزَّن، vmin, vmax,
# تدرّج ألوان [(موضع 0..1, (r,g,b))]). المعاملات من توثيق SoilGrids الرسميّ.
_SEQ_GREEN = [(0.0, (247, 252, 245)), (0.5, (116, 196, 118)), (1.0, (0, 68, 27))]
_SEQ_BROWN = [(0.0, (247, 240, 230)), (0.5, (191, 148, 92)), (1.0, (102, 60, 20))]
_SEQ_ORANGE = [(0.0, (255, 247, 236)), (0.5, (253, 187, 132)), (1.0, (179, 0, 0))]
# pH متبايِن: حمضيّ (أحمر) → متعادل (أخضر) → قلويّ (أزرق) — دلالة زراعيّة.
_DIV_PH = [
    (0.0, (215, 48, 39)),
    (0.35, (253, 174, 97)),
    (0.5, (26, 152, 80)),
    (0.7, (69, 117, 180)),
    (1.0, (49, 54, 149)),
]

SOIL_PROPERTIES: dict[str, dict] = {
    "phh2o": {
        "name_ar": "الحموضة pH",
        "unit": "pH",
        "div": 10.0,
        "vmin": 3.5,
        "vmax": 9.0,
        "ramp": _DIV_PH,
    },
    "clay": {
        "name_ar": "الطين",
        "unit": "%",
        "div": 10.0,
        "vmin": 0.0,
        "vmax": 60.0,
        "ramp": _SEQ_BROWN,
    },
    "sand": {
        "name_ar": "الرمل",
        "unit": "%",
        "div": 10.0,
        "vmin": 0.0,
        "vmax": 100.0,
        "ramp": _SEQ_ORANGE,
    },
    "silt": {
        "name_ar": "الطمي",
        "unit": "%",
        "div": 10.0,
        "vmin": 0.0,
        "vmax": 80.0,
        "ramp": _SEQ_BROWN,
    },
    "soc": {
        "name_ar": "الكربون العضويّ",
        "unit": "g/kg",
        "div": 10.0,
        "vmin": 0.0,
        "vmax": 40.0,
        "ramp": _SEQ_GREEN,
    },
    "cec": {
        "name_ar": "السعة التبادليّة CEC",
        "unit": "cmol(c)/kg",
        "div": 10.0,
        "vmin": 0.0,
        "vmax": 50.0,
        "ramp": _SEQ_GREEN,
    },
    "nitrogen": {
        "name_ar": "النيتروجين",
        "unit": "g/kg",
        "div": 100.0,
        "vmin": 0.0,
        "vmax": 5.0,
        "ramp": _SEQ_GREEN,
    },
    "bdod": {
        "name_ar": "الكثافة الظاهريّة",
        "unit": "g/cm³",
        "div": 100.0,
        "vmin": 0.8,
        "vmax": 1.8,
        "ramp": _SEQ_BROWN,
    },
}

DISCLAIMER_AR = (
    "طبقة تقديريّة من SoilGrids (ISRIC، ~250م). للتوجيه في اختيار مواقع العيّنات فقط — "
    "لا تُغني عن التحليل المختبريّ ولا تصلح وحدها لقرار داخل حقل صغير."
)


def _ramp_lut(ramp: list[tuple[float, tuple[int, int, int]]]):
    import numpy as np

    lut = np.zeros((256, 3), dtype="uint8")
    for i in range(256):
        t = i / 255.0
        # ابحث عن القطعة المحتوية t
        for k in range(len(ramp) - 1):
            t0, c0 = ramp[k]
            t1, c1 = ramp[k + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                lut[i] = [round(c0[j] + (c1[j] - c0[j]) * f) for j in range(3)]
                break
        else:
            lut[i] = ramp[-1][1]
    return lut


def supported_properties() -> list[dict]:
    """قائمة الخصائص المدعومة + الوحدة + المدى (للواجهة). لا تعكس توفّر المصدر."""
    return [
        {"key": k, "name_ar": v["name_ar"], "unit": v["unit"], "vmin": v["vmin"], "vmax": v["vmax"]}
        for k, v in SOIL_PROPERTIES.items()
    ]


def soil_legend(prop: str) -> list[dict]:
    """أسطورة تدرّج خاصّيّة (5 محطّات لون + قيمة) — من ramp/vmin/vmax نفسها."""
    meta = SOIL_PROPERTIES.get(prop)
    if not meta:
        return []
    lut = _ramp_lut(meta["ramp"])
    out = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        val = meta["vmin"] + (meta["vmax"] - meta["vmin"]) * frac
        rgb = lut[min(255, max(0, int(frac * 255)))]
        out.append(
            {"value": round(float(val), 2), "color": f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"}
        )
    return out


# مرادفات أسماء الخصائص (مرونة تسمية عند التزويد) — تُطبَّع إلى مفاتيح SOIL_PROPERTIES.
_PROPERTY_ALIASES: dict[str, str] = {
    "ph": "phh2o",
    "organic_carbon": "soc",
    "oc": "soc",
    "bulk_density": "bdod",
    "n": "nitrogen",
}


def normalize_property(prop: str) -> str | None:
    """يطبّع اسم الخاصّيّة (مع المرادفات) إلى مفتاح مدعوم، أو None."""
    p = (prop or "").strip().lower().replace("-", "_")
    p = _PROPERTY_ALIASES.get(p, p)
    return p if p in SOIL_PROPERTIES else None


def soil_raster_path(prop: str, depth: str) -> str | None:
    """يحلّ مسار GeoTIFF لـ(خاصّيّة، عمق) عبر أنماط تهيئة متعدّدة — أو None (بلا تلفيق).

    الأولويّة (مرونة التزويد): (1) مسار صريح ``SOILGRID_<PROP>_<DEPTH>_PATH``؛ (2) قالب
    ``SOIL_LAYER_PATH_TEMPLATE`` (``{property}``/``{depth}``)؛ (3) مجلّد
    ``SOILGRIDS_DIR``/``SOILGRIDS_COG_DIR``/``SOIL_COG_DIR`` بأسماء مرشّحة.
    """
    prop = normalize_property(prop) or ""
    if prop not in SOIL_PROPERTIES or depth not in SOIL_DEPTHS:
        return None

    explicit = os.getenv(f"SOILGRID_{prop.upper()}_{depth.upper().replace('-', '_')}_PATH")
    if explicit:
        return explicit if os.path.isfile(explicit) else None

    template = os.getenv("SOIL_LAYER_PATH_TEMPLATE")
    if template:
        try:
            path = template.format(property=prop, depth=depth, prop=prop)
        except (KeyError, IndexError, ValueError):
            path = ""
        return path if path and os.path.isfile(path) else None

    base = os.getenv("SOILGRIDS_DIR") or os.getenv("SOILGRIDS_COG_DIR") or os.getenv("SOIL_COG_DIR")
    if not base:
        return None
    for name in (f"{prop}_{depth}.tif", f"{prop}_{depth.replace('-', '_')}.tif"):
        cand = os.path.join(base, name)
        if os.path.isfile(cand):
            return cand
    nested = os.path.join(base, prop, f"{depth}.tif")
    return nested if os.path.isfile(nested) else None


def render_soil_tile(prop: str, depth: str, z: int, x: int, y: int) -> bytes | None:
    """بلاطة خاصّيّة تربة (PNG ملوّن شبه-شفّاف) من SoilGrids raster. ``None`` ⇒ شفّاف صادق."""
    meta = SOIL_PROPERTIES.get(prop)
    path = soil_raster_path(prop, depth)
    if meta is None or path is None:
        return None
    try:
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.warp import Resampling, reproject, transform_bounds
    except Exception:  # noqa: BLE001 — مكتبات غير متوفّرة ⇒ شفّاف صادق
        return None

    from tile_render import TILE_SIZE, encode_png_rgba, tile_bounds_3857

    minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)
    dst_crs = "EPSG:3857"
    dst_transform = from_bounds(minx, miny, maxx, maxy, TILE_SIZE, TILE_SIZE)
    try:
        with rasterio.open(path) as src:
            try:
                cb = transform_bounds(src.crs, dst_crs, *src.bounds)
                if cb[2] < minx or cb[0] > maxx or cb[3] < miny or cb[1] > maxy:
                    return None
            except Exception:  # noqa: BLE001
                pass
            dst = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype="float32")
            reproject(
                source=rasterio.band(src, 1),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.nearest,  # قيم فئويّة/شبكيّة 250م ⇒ nearest (لا اختلاق تدرّج)
                src_nodata=src.nodata,
                dst_nodata=np.nan,
            )
    except Exception:  # noqa: BLE001
        return None

    if not np.isfinite(dst).any():
        return None

    real = dst / float(meta["div"])  # الوحدة المُخزّنة ⇒ التقليديّة (معامل SoilGrids)
    vmin, vmax = float(meta["vmin"]), float(meta["vmax"])
    norm = np.clip((real - vmin) / (vmax - vmin if vmax > vmin else 1.0), 0.0, 1.0)
    idx = np.nan_to_num(norm * 255.0, nan=0.0).astype("uint8")
    lut = _ramp_lut(meta["ramp"])
    valid = np.isfinite(real)
    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype="uint8")
    rgba[..., 0] = lut[idx, 0]
    rgba[..., 1] = lut[idx, 1]
    rgba[..., 2] = lut[idx, 2]
    rgba[..., 3] = np.where(valid, 190, 0).astype("uint8")  # شبه-شفّاف فوق الخريطة
    return encode_png_rgba(rgba)


def normalize_depth(depth: str | None) -> str:
    """يطبّع العمق إلى أحد الأعماق الستّة المعياريّة (الافتراض: السطحيّ 0-5cm)."""
    d = (depth or "").strip()
    return d if d in SOIL_DEPTHS else SOIL_DEPTHS[0]


def is_source_configured() -> bool:
    """هل أيّ نمط تهيئة مصدر SoilGrids مضبوط (مجلّد/قالب/مسار صريح)؟"""
    if os.getenv("SOIL_LAYER_PATH_TEMPLATE"):
        return True
    for base_env in ("SOILGRIDS_DIR", "SOILGRIDS_COG_DIR", "SOIL_COG_DIR"):
        base = os.getenv(base_env)
        if base and os.path.isdir(base):
            return True
    return any(k.startswith("SOILGRID_") and k.endswith("_PATH") for k in os.environ)


def read_property_bbox(prop: str, depth: str, bbox: list[float]):
    """يقرأ نافذة خاصّيّة تربة على bbox الحقل ويحوّلها للوحدة التقليديّة (÷div).

    يُرجِع مصفوفة float32 بـNaN للـnodata، أو ``None`` (بلا مصدر/خارج التغطية) — بلا تلفيق.
    """
    meta = SOIL_PROPERTIES.get(prop)
    path = soil_raster_path(prop, depth)
    if meta is None or path is None or not bbox or len(bbox) != 4:
        return None
    try:
        import numpy as np
        import rasterio
        from tile_render import read_field_window
    except Exception:  # noqa: BLE001
        return None
    try:
        with rasterio.open(path) as src:
            res = read_field_window(src, bbox)  # CRS-correct + مسقوف الحجم
    except Exception:  # noqa: BLE001
        return None
    if res is None:
        return None
    arr, _sx, _sy = res
    if arr.size == 0 or not np.isfinite(arr).any():
        return None
    return arr / float(meta["div"])


def usda_texture_class(clay_pct: float | None, sand_pct: float | None) -> str | None:
    """صنف قوام USDA من نسبتَي الطين والرمل (٪) — مثلّث القوام القياسيّ (مبسّط)."""
    if clay_pct is None or sand_pct is None:
        return None
    c, s = float(clay_pct), float(sand_pct)
    silt = max(0.0, 100.0 - c - s)
    if c >= 40 and s <= 45 and silt < 40:
        return "طينيّ (clay)"
    if c >= 27 and c < 40 and s <= 45:
        return "طينيّ مزيجيّ (clay loam)" if s > 20 else "طينيّ غرينيّ مزيجيّ (silty clay loam)"
    if c >= 35 and s >= 45:
        return "طينيّ رمليّ (sandy clay)"
    if s >= 85 and c < 10:
        return "رمليّ (sand)"
    if s >= 70 and c < 15:
        return "رمليّ مزيجيّ (loamy sand)"
    if silt >= 80 and c < 12:
        return "غرينيّ (silt)"
    if silt >= 50 and c < 27:
        return "غرينيّ مزيجيّ (silt loam)"
    if s >= 45 and c < 20:
        return "مزيجيّ رمليّ (sandy loam)"
    return "مزيجيّ (loam)"


def compute_field_soil_summary(bbox: list[float] | None, depth: str = "0-5cm") -> dict:
    """ملخّص خصائص التربة لحقلٍ (متوسّطات SoilGrids على bbox) + صنف القوام + تحذير.

    صدق: بلا مصدر/تغطية ⇒ ``computed:false`` + سبب — لا تلفيق. توجيهيّ لاختيار العيّنات.
    """
    empty = {"computed": False, "properties": {}}
    if not is_source_configured():
        return {**empty, "source": "soilgrids-source-not-configured"}
    if not bbox or len(bbox) != 4:
        return {**empty, "source": "field-bbox-unavailable"}
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        return {**empty, "source": "runtime-libs-missing"}
    depth = normalize_depth(depth)
    props: dict[str, dict] = {}
    for prop, meta in SOIL_PROPERTIES.items():
        arr = read_property_bbox(prop, depth, bbox)
        if arr is None:
            continue
        finite = arr[np.isfinite(arr)]
        if not finite.size:
            continue
        props[prop] = {
            "mean": round(float(finite.mean()), 2),
            "min": round(float(finite.min()), 2),
            "max": round(float(finite.max()), 2),
            "unit": meta["unit"],
            "name_ar": meta["name_ar"],
        }
    if not props:
        return {**empty, "source": "field-outside-source"}
    texture = usda_texture_class(
        props.get("clay", {}).get("mean"), props.get("sand", {}).get("mean")
    )
    return {
        "computed": True,
        "source": "soilgrids",
        "depth": depth,
        "properties": props,
        "texture_class": texture,
        "disclaimer": DISCLAIMER_AR,
    }
