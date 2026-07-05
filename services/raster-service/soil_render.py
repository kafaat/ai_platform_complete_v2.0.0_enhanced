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
SOIL_DEPTHS: tuple[str, ...] = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")

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


def soil_raster_path(prop: str, depth: str) -> str | None:
    """يحلّ مسار GeoTIFF لـ(خاصّيّة، عمق) من ``SOILGRIDS_DIR`` — أو None (بلا تلفيق)."""
    base = os.getenv("SOILGRIDS_DIR")
    if not base or prop not in SOIL_PROPERTIES or depth not in SOIL_DEPTHS:
        return None
    path = os.path.join(base, f"{prop}_{depth}.tif")
    return path if os.path.isfile(path) else None


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
    """هل مجلّد SoilGrids مُهيّأ أصلاً (بصرف النظر عن ملفّ بعينه)؟"""
    base = os.getenv("SOILGRIDS_DIR")
    return bool(base and os.path.isdir(base))
