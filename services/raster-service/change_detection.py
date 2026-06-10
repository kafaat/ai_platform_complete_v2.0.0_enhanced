"""
change_detection.py — كشف التغيير المكاني بين تاريخين (per-pixel 2D change).

الفجوة المُسدَّة: النظام يملك تحليلاً زمنيّاً 1D غنيّاً (time_series.py: composites
شهريّة، اتّجاه، شذوذ z-score) يجيب «هل متوسّط المؤشّر تغيّر؟». لكنّه لم يكن يجيب
«أين بالضبط (أيّ بكسلات/مناطق) تدهور الحقل بين تاريخ A و B، وبأيّ شدّة؟». المتوسّط
الزمني يُخفي التدهور الموضعي (زحف ملوحة من زاوية، عطل ريّ في قطاع) لأنّ ربع الحقل
قد يموت بينما المتوسّط يبقى مقبولاً.

هذه الوحدة نقيّة (numpy فقط، لا I/O) وحتميّة. تستقبل شبكتي مؤشّر للتاريخين
(تُحسبان upstream من COG عبر rasterio في العامل — لا تخترع قيماً) وتُنتج خريطة
فرق بكسل-بكسل مُصنّفة، مع احترام اتّجاه المؤشّر وصدق فجوات السحاب (NaN/None لا
تُحسب ولا يُفبرَك تغيير عبرها).
"""

from __future__ import annotations

# المؤشّرات حيث القيمة الأعلى = أسوأ (تدهور): الملوحة. الباقي (ندوة/رطوبة/مياه):
# القيمة الأدنى = أسوأ. يطابق _HIGH_IS_SEVERE في indicator_grid (مصدر واحد للدلالة).
_HIGHER_IS_WORSE = {"salinity", "ndsi"}

# تغطية صالحة دونها تُعتبر النتيجة جزئيّة (غيوم/فجوات) ويُرفع تحذير.
_COVERAGE_WARN_BELOW = 0.6

# رموز التغيير العدديّة للموبايل (تلوين الخريطة).
CODE_SEVERE_DEGRADATION = -2
CODE_DEGRADATION = -1
CODE_STABLE = 0
CODE_IMPROVEMENT = 1

_CODE_TO_CLASS = {
    CODE_SEVERE_DEGRADATION: "severe_degradation",
    CODE_DEGRADATION: "degradation",
    CODE_STABLE: "stable",
    CODE_IMPROVEMENT: "improvement",
}


def _to_float_array(grid):
    """يحوّل شبكة list[list[float|None]] (أو مصفوفة) إلى numpy float بـNaN للفجوات."""
    import numpy as np

    if hasattr(grid, "shape"):  # مصفوفة numpy أصلاً
        return np.asarray(grid, dtype="float64")
    return np.array(
        [[float("nan") if v is None else float(v) for v in row] for row in grid],
        dtype="float64",
    )


def _classify_pixel(delta: float, higher_is_worse: bool, slight: float, severe: float) -> int:
    """يصنّف بكسلاً واحداً حسب فرق المؤشّر (after-before) واتّجاهه وشدّته."""
    mag = abs(delta)
    if mag < slight:
        return CODE_STABLE
    # الأثر: للملوحة الزيادة(+) تدهور؛ للنبات النقص(−) تدهور.
    worsening = (delta > 0) if higher_is_worse else (delta < 0)
    if worsening:
        return CODE_SEVERE_DEGRADATION if mag >= severe else CODE_DEGRADATION
    return CODE_IMPROVEMENT


def _zones_from_codes(code_grid, delta_grid, rows: int, cols: int) -> list[dict]:
    """يجمّع خلايا كلّ صنف تغيير في منطقة (للموبايل: أين تدهور/تحسّن الحقل)."""
    buckets: dict[int, list] = {}
    sums: dict[int, float] = {}
    for r in range(rows):
        for c in range(cols):
            code = code_grid[r][c]
            if code is None or code == CODE_STABLE:
                continue
            buckets.setdefault(code, []).append([r, c])
            sums[code] = sums.get(code, 0.0) + delta_grid[r][c]
    zones = []
    for code in (CODE_SEVERE_DEGRADATION, CODE_DEGRADATION, CODE_IMPROVEMENT):
        cells = buckets.get(code)
        if not cells:
            continue
        zones.append(
            {
                "class": _CODE_TO_CLASS[code],
                "code": code,
                "count": len(cells),
                "mean_delta": round(sums[code] / len(cells), 4),
                "cells": cells,
            }
        )
    return zones


def _interpret_ar(
    index: str,
    coverage: float,
    mean_delta: float,
    severe_pct: float,
    degraded_pct: float,
    improved_pct: float,
    cloud_warning: bool,
) -> str:
    """تفسير عربي موجز — يُبرز التدهور الموضعي الذي يُخفيه المتوسّط."""
    if coverage <= 0.0:
        return "لا بكسلات صالحة للمقارنة (تغطية صفر — غيوم أو فجوات بين التاريخين)."

    parts: list[str] = []
    salinity = index in _HIGHER_IS_WORSE
    if degraded_pct >= 5.0:
        lead = "زحف ملوحة محتمل: " if salinity else ""
        parts.append(f"{lead}تدهور {degraded_pct}% من الحقل ({severe_pct}% منها بشدّة)")
        # الرؤية الأساسيّة: المتوسّط يبدو سليماً بينما رقعة تدهورت بشدّة.
        if abs(mean_delta) < 0.1 and severe_pct >= 10.0:
            parts.append(
                f"المتوسّط ({mean_delta:+.3f}) يبدو مستقرّاً، لكنّ التدهور موضعيّ "
                "يُخفيه المتوسّط — راجع خريطة الفرق لتحديد الرقعة"
            )
    if improved_pct >= 5.0:
        parts.append(f"تحسّن {improved_pct}% من الحقل")
    if not parts:
        parts.append("لا تغيّر مكانيّ ملموس بين التاريخين (الحقل مستقرّ)")
    msg = "؛ ".join(parts) + "."
    if cloud_warning:
        msg += f" ⚠️ التغطية {round(coverage * 100, 1)}% فقط — نتيجة جزئيّة (غيوم/فجوات)."
    return msg


def detect_change(
    before,
    after,
    *,
    index: str = "ndvi",
    slight_threshold: float = 0.1,
    severe_threshold: float = 0.2,
) -> dict:
    """يكشف التغيير المكاني بين شبكتي مؤشّر لتاريخين (نفس الأبعاد).

    Parameters
    ----------
    before, after:
        شبكتا المؤشّر (list[list[float|None]] أو numpy) لتاريخين، نفس الأبعاد.
        None/NaN = فجوة (غيمة/خارج الحقل) — لا تُحسب.
    index:
        نوع المؤشّر (يحدّد الاتّجاه: ملوحة ⇒ الارتفاع تدهور؛ غيرها ⇒ النقص تدهور).
    slight_threshold, severe_threshold:
        عتبتا |الفرق| لتصنيف التغيّر (طفيف/حادّ). من الأدبيّات العامّة — عايِرها
        بأزواج حقيقيّة من الميدان.

    Returns
    -------
    dict
        خريطة فرق بكسل-بكسل مُصنّفة + إحصاءات + نسب المساحة + مناطق + تفسير عربي.
        يرفع ValueError إن اختلفت أبعاد الشبكتين.
    """
    import numpy as np

    b = _to_float_array(before)
    a = _to_float_array(after)
    if b.shape != a.shape:
        raise ValueError(f"شكل الشبكتين مختلف: before={b.shape} after={a.shape}")
    if b.ndim != 2:
        raise ValueError("الشبكتان يجب أن تكونا ثنائيّتي الأبعاد (rows×cols)")

    rows, cols = (int(b.shape[0]), int(b.shape[1])) if b.size else (0, 0)
    total = rows * cols
    higher_is_worse = index in _HIGHER_IS_WORSE
    slight = abs(float(slight_threshold))
    severe = max(abs(float(severe_threshold)), slight)

    valid_mask = np.isfinite(b) & np.isfinite(a)
    delta = np.where(valid_mask, a - b, np.nan)

    delta_grid: list[list] = []
    code_grid: list[list] = []
    counts = {
        CODE_SEVERE_DEGRADATION: 0,
        CODE_DEGRADATION: 0,
        CODE_STABLE: 0,
        CODE_IMPROVEMENT: 0,
    }
    for r in range(rows):
        d_row, code_row = [], []
        for c in range(cols):
            if not valid_mask[r, c]:
                d_row.append(None)
                code_row.append(None)
                continue
            dv = float(delta[r, c])
            code = _classify_pixel(dv, higher_is_worse, slight, severe)
            counts[code] += 1
            d_row.append(round(dv, 4))
            code_row.append(code)
        delta_grid.append(d_row)
        code_grid.append(code_row)

    valid = int(valid_mask.sum())
    coverage = (valid / total) if total else 0.0
    finite_delta = delta[np.isfinite(delta)]
    if finite_delta.size:
        mean_delta = round(float(finite_delta.mean()), 4)
        stats = {
            "mean_delta": mean_delta,
            "min_delta": round(float(finite_delta.min()), 4),
            "max_delta": round(float(finite_delta.max()), 4),
        }
    else:
        mean_delta = 0.0
        stats = {"mean_delta": 0.0, "min_delta": 0.0, "max_delta": 0.0}

    def _pct(n: int) -> float:
        return round(100.0 * n / valid, 2) if valid else 0.0

    severe_pct = _pct(counts[CODE_SEVERE_DEGRADATION])
    degraded_pct = _pct(counts[CODE_SEVERE_DEGRADATION] + counts[CODE_DEGRADATION])
    improved_pct = _pct(counts[CODE_IMPROVEMENT])
    stable_pct = _pct(counts[CODE_STABLE])
    cloud_warning = coverage < _COVERAGE_WARN_BELOW

    return {
        "index": index,
        "direction": "higher_is_worse" if higher_is_worse else "lower_is_worse",
        "rows": rows,
        "cols": cols,
        "delta_grid": delta_grid,  # after - before (None للفجوات)
        "change_grid": code_grid,  # -2/-1/0/1 (None للفجوات) للموبايل
        "stats": stats,
        "coverage_pct": round(coverage * 100, 2),
        "valid_pixels": valid,
        "total_pixels": total,
        "areas": {
            "severe_degraded_pct": severe_pct,
            "degraded_pct": degraded_pct,
            "improved_pct": improved_pct,
            "stable_pct": stable_pct,
        },
        "zones": _zones_from_codes(code_grid, delta_grid, rows, cols),
        "thresholds": {"slight": slight, "severe": severe},
        "cloud_warning": cloud_warning,
        "interpretation_ar": _interpret_ar(
            index, coverage, mean_delta, severe_pct, degraded_pct, improved_pct, cloud_warning
        ),
    }
