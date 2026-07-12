"""
indicator_grid.py — شبكة المؤشّر لكلّ بكسل (per-pixel indicator grid) للموبايل.

يقرأ COG محسوباً للحقل، يصغّره إلى شبكة grid×grid بمتوسّط الكتل (block-mean)
متجاهلاً NaN، ويصنّف مناطق الشدّة (low/medium/high). لا يحتوي هذا الملف أي
مولّد تركيبي؛ غياب المنتج الحقيقي يُعالج في الراوتر بفشل مغلق.

العقد المُعاد (يعتمده الـfrontend حرفيّاً):
  {field_id, index, date, bbox:[minlon,minlat,maxlon,maxlat], rows, cols,
   grid:[[float|null,...],...], stats:{min,max,mean},
   zones:[{id,severity,mean,cells:[[r,c],...]}], source, real_data}
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


def _severity_thresholds(index: str) -> tuple[float, float]:
    """عتبات بسيطة (low<lo, lo<=med<hi, high>=hi) لتصنيف الشدّة حسب المؤشّر.

    للمؤشّرات النباتيّة (ndvi/ndmi/ndwi): قيمة منخفضة = شدّة إجهاد عالية.
    للملوحة (salinity/ndsi): قيمة عالية = شدّة عالية. التصنيف هنا على القيمة
    الخام؛ ربط القيمة بالشدّة يتمّ في _classify_zones حسب اتّجاه المؤشّر.
    """
    table = {
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
    return table.get(index, (0.3, 0.6))


# المؤشّرات حيث القيمة العالية = شدّة عالية (ملوحة). الباقي: القيمة المنخفضة = شدّة عالية.
_HIGH_IS_SEVERE = {"salinity", "ndsi"}


def classify_zones(grid_vals, index: str, rows: int, cols: int) -> list[dict]:
    """يصنّف خلايا الشبكة إلى مناطق شدّة (low/medium/high) ويجمّع خلاياها.

    grid_vals: قائمة rows من قوائم cols (float أو None).
    يُرجِع قائمة zones: [{id, severity, mean, cells:[[r,c],...]}].
    """
    lo, hi = _severity_thresholds(index)
    high_severe = index in _HIGH_IS_SEVERE

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


def grid_from_array(arr, index: str, grid: int) -> dict:
    """يحوّل مصفوفة مؤشّر 2D (numpy، NaN=خارج الحقل) إلى عقد شبكة الموبايل.

    يُرجِع dict جزئيّاً: {rows, cols, grid, stats, zones}. الحقول bbox/date/
    source/real_data تُضاف في المُستدعي (يعرف الحقل والمصدر).
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

    finite = down[np.isfinite(down)]
    if finite.size:
        stats = {
            "min": round(float(finite.min()), 4),
            "max": round(float(finite.max()), 4),
            "mean": round(float(finite.mean()), 4),
        }
    else:
        stats = {"min": 0.0, "max": 0.0, "mean": 0.0}

    zones = classify_zones(grid_vals, index, rows, cols)
    return {"rows": rows, "cols": cols, "grid": grid_vals, "stats": stats, "zones": zones}
