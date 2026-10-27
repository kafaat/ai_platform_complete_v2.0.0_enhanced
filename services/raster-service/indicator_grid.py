"""
indicator_grid.py — شبكة المؤشّر لكلّ بكسل (per-pixel indicator grid) للموبايل.

يقرأ COG محسوباً للحقل، يصغّره إلى شبكة grid×grid بمتوسّط الكتل (block-mean)
متجاهلاً NaN، ويصنّف مناطق الشدّة (low/medium/high). لا يحتوي هذا الملف أي
مولّد تركيبي؛ غياب المنتج الحقيقي يُعالج في الراوتر بفشل مغلق.

العقد المُعاد (يعتمده الـfrontend حرفيّاً):
  {field_id, index, date, bbox:[minlon,minlat,maxlon,maxlat], rows, cols,
   grid:[[float|null,...],...], stats:{min,max,mean},
   zones:[{id,severity,mean,cells:[[r,c],...]}], source, real_data}

إضافات (لا تكسر العقد): ``stats`` إحصاء الحقل من بكسلات المصدر الصالحة
(``stats_basis="source_pixels"``)، و``grid_stats`` إحصاء خلايا العرض المُصغَّرة منفصلاً،
و``severity_supported=false`` لمؤشّر بلا عتبات شدّة مُعلَنة (zones فارغة).
"""

from __future__ import annotations


def _block_mean_downsample(arr, grid: int):
    """يصغّر مصفوفة 2D إلى grid×grid بمتوسّط الكتل متجاهلاً NaN.

    يُرجِع (out, rows, cols) حيث out مصفوفة numpy float بقيم NaN للكتل الفارغة.
    يستخدم numpy إن توفّر؛ يُفترض توفّره (يُستدعى فقط في المسار الحقيقي).
    """
    import numpy as np

    h, w = arr.shape
    rows = min(grid, h) if h else 0
    cols = min(grid, w) if w else 0
    if rows == 0 or cols == 0:
        return np.full((0, 0), np.nan, dtype="float64"), 0, 0

    out = np.full((rows, cols), np.nan, dtype="float64")
    # حدود الكتل (تقسيم متساوٍ تقريبيّاً يغطّي كلّ البكسلات)
    r_edges = [int(round(i * h / rows)) for i in range(rows + 1)]
    c_edges = [int(round(j * w / cols)) for j in range(cols + 1)]
    for r in range(rows):
        r0, r1 = r_edges[r], max(r_edges[r] + 1, r_edges[r + 1])
        r1 = min(r1, h)
        for c in range(cols):
            c0, c1 = c_edges[c], max(c_edges[c] + 1, c_edges[c + 1])
            c1 = min(c1, w)
            block = arr[r0:r1, c0:c1]
            finite = block[np.isfinite(block)]
            if finite.size:
                out[r, c] = float(finite.mean())
    return out, rows, cols


# عتبات الشدّة (lo, hi) لكلّ مؤشّر **مُعلَن** فقط. لا عتبة افتراضيّة: مؤشّر غير مُدرَج هنا
# (msi/bsi/savi/…) شدّته «غير معروفة» فلا تُصنَّف مناطقه — كان يرث عتبات NDVI (0.3/0.6)
# فيُوسَم MSI=1.5 «low» بينما يلوّنه المُصيِّر أحمر (T9).
_SEVERITY_THRESHOLDS: dict[str, tuple[float, float]] = {
    "ndvi": (0.3, 0.6),
    "ndmi": (0.0, 0.3),
    "ndwi": (-0.3, 0.0),
    "salinity": (0.1, 0.3),
    "ndsi": (0.1, 0.3),
    # المؤشّرات الموسّعة (Sprint 5b)
    "msavi": (0.3, 0.6),  # مثل ndvi (تصحيح تربة)
    "evi": (0.2, 0.4),
    "ndre": (0.2, 0.4),  # red-edge — نطاق أضيق
    "moisture": (0.0, 0.3),  # NDMI-style مثل ndmi
}


def _severity_thresholds(index: str) -> tuple[float, float] | None:
    """عتبات بسيطة (low<lo, lo<=med<hi, high>=hi) لتصنيف الشدّة حسب المؤشّر.

    التصنيف هنا على القيمة الخام؛ ربط القيمة بالشدّة يتمّ في classify_zones حسب
    اتّجاه المؤشّر. ``None`` ⇒ مؤشّر بلا عتبات مُعلَنة (شدّة غير معروفة، لا تخمين).
    """
    return _SEVERITY_THRESHOLDS.get(index)


def _high_is_severe(index: str) -> bool:
    """اتّجاه الشدّة من قاموس المُصيِّر نفسه (``tile_render._INDEX_DOMAIN``: invert ⇒
    القيمة العالية أسوأ وتُلوَّن أحمر) — مصدر واحد للتلوين والتصنيف فلا يتناقضان."""
    from tile_render import _INDEX_DOMAIN

    domain = _INDEX_DOMAIN.get(index)
    return bool(domain[2]) if domain is not None else False


def classify_zones(grid_vals, index: str, rows: int, cols: int) -> list[dict]:
    """يصنّف خلايا الشبكة إلى مناطق شدّة (low/medium/high) ويجمّع خلاياها.

    grid_vals: قائمة rows من قوائم cols (float أو None).
    يُرجِع قائمة zones: [{id, severity, mean, cells:[[r,c],...]}]؛ وقائمة فارغة لمؤشّر
    بلا عتبات مُعلَنة (شدّة غير معروفة — لا عتبات NDVI بديلة).
    """
    thresholds = _severity_thresholds(index)
    if thresholds is None:
        return []
    lo, hi = thresholds
    high_severe = _high_is_severe(index)

    buckets: dict[str, list[tuple[int, int]]] = {"low": [], "medium": [], "high": []}
    sums: dict[str, float] = {"low": 0.0, "medium": 0.0, "high": 0.0}
    for r in range(rows):
        for c in range(cols):
            v = grid_vals[r][c]
            if v is None:
                continue
            if high_severe:
                sev = "high" if v >= hi else ("medium" if v >= lo else "low")
            else:
                sev = "high" if v < lo else ("medium" if v < hi else "low")
            buckets[sev].append([r, c])
            sums[sev] += v

    zones = []
    for sev in ("low", "medium", "high"):
        cells = buckets[sev]
        if not cells:
            continue
        zones.append(
            {
                "id": f"zone_{sev}",
                "severity": sev,
                "mean": round(sums[sev] / len(cells), 4),
                "cells": cells,
            }
        )
    return zones


def _finite_stats(values) -> dict:
    """min/max/mean لقيم منتهية (finite) مُقرَّبة إلى 4 منازل؛ None عند الفراغ."""
    import numpy as np

    finite = values[np.isfinite(values)]
    if not finite.size:
        return {"min": None, "max": None, "mean": None}
    return {
        "min": round(float(finite.min()), 4),
        "max": round(float(finite.max()), 4),
        "mean": round(float(finite.mean()), 4),
    }


def source_pixel_stats(src, band: int = 1) -> dict:
    """إحصاء الحقل العلميّ من بكسلات المصدر **الأصليّة** الصالحة لـdataset rasterio مفتوح.

    يُقرأ كتلةً كتلةً (block_windows) فيبقى استهلاك الذاكرة محدوداً، ويحترم nodata
    والقناع الداخليّ (masked=True). كلّ بكسل صالح وزنه 1 — بخلاف متوسّط خلايا العرض
    المُصغَّرة (كلّ خلية وزنها 1 مهما قلّ عدد بكسلاتها الصالحة، T8).
    """
    import numpy as np

    total, count = 0.0, 0
    lo, hi = float("inf"), float("-inf")
    for _, window in src.block_windows(band):
        block = src.read(band, window=window, masked=True).astype("float64").filled(np.nan)
        if src.nodata is not None:
            block = np.where(block == src.nodata, np.nan, block)
        finite = block[np.isfinite(block)]
        if finite.size:
            total += float(finite.sum())
            count += int(finite.size)
            lo = min(lo, float(finite.min()))
            hi = max(hi, float(finite.max()))
    if not count:
        return {"min": None, "max": None, "mean": None}
    return {"min": round(lo, 4), "max": round(hi, 4), "mean": round(total / count, 4)}


def grid_from_array(arr, index: str, grid: int, *, field_stats: dict | None = None) -> dict:
    """يحوّل مصفوفة مؤشّر 2D (numpy، NaN=خارج الحقل) إلى عقد شبكة الموبايل.

    يُرجِع dict جزئيّاً: {rows, cols, grid, stats, stats_basis, grid_stats, zones,
    severity_supported}. الحقول bbox/date/source/real_data تُضاف في المُستدعي.

    ``stats`` إحصاء الحقل العلميّ من بكسلات المصدر (``arr`` نفسها، أو ``field_stats``
    حين يمرّر المُستدعي مصفوفة مُصغَّرة مسبقاً ويحسب الإحصاء من المصدر). ``grid_stats``
    إحصاء خلايا العرض (متوسّط غير موزون للخلايا) — للعرض فقط، يتغيّر بتغيّر ``grid``.
    """
    import numpy as np

    down, rows, cols = _block_mean_downsample(arr, grid)
    grid_vals: list[list] = []
    for r in range(rows):
        row_out = []
        for c in range(cols):
            v = down[r, c]
            row_out.append(None if (v is None or not np.isfinite(v)) else round(float(v), 4))
        grid_vals.append(row_out)

    stats = dict(field_stats) if field_stats is not None else _finite_stats(np.asarray(arr))
    zones = classify_zones(grid_vals, index, rows, cols)
    return {
        "rows": rows,
        "cols": cols,
        "grid": grid_vals,
        "stats": stats,
        "stats_basis": "source_pixels",
        "grid_stats": _finite_stats(down),
        "zones": zones,
        "severity_supported": _severity_thresholds(index) is not None,
    }
