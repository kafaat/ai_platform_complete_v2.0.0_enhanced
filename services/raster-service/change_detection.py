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

# اتّجاه المؤشّر لكشف التغيّر — ثلاثة أصناف صريحة (S3-b: اسم خارجها يُرفض ValueError ⇒ 422
# على الحدود بدل أن يسقط صامتاً على «الأدنى أسوأ» فيقلب التدهور تحسّناً):
#
# • القيمة الأعلى = أسوأ: الملوحة (salinity/ndsi)، و**مؤشّرات الإجهاد المائيّ بتعريفها**:
#   MSI = SWIR/NIR (B11/B08) يرتفع بنقص ماء الورقة؛ CWSI = مؤشّر إجهاد مائيّ للمحصول
#   (0 = بلا إجهاد، 1 = إجهاد أقصى)؛ TVDI = مؤشّر جفاف حرارة–نبات (0 رطب، 1 جاف). كانت
#   الثلاثة في «الأدنى أسوأ» فيُوسَم تفاقم الإجهاد «تحسّناً» — حُسِم بتعريفاتها (لا تخمين)،
#   ويطابق tile_render._INDEX_DOMAIN (invert=True لـmsi/cwsi/tvdi) الذي تشتقّ منه شدّة
#   indicator_grid.
# • الاتّجاه يتبع السياق (لا حكم عامّ تحسّن/تدهور): تربة عارية/سطوع/حراثة (bsi/bi/bi2/dbsi/
#   ndti) — ارتفاعها قد يكون تدهور غطاء أو حراثة/حصاد مقصودين؛ وLST — ارتفاعها إجهاد حراريّ
#   في الصيف وقد يكون موسميّاً محضاً. يُحفَظ فرق البكسل وإحصاؤه ويُحجَب وسم التحسّن/التدهور
#   مع سبب صريح (index_direction_context_dependent). بقي مفتوحاً: ربط اتّجاهها بالموسم/مرحلة
#   المحصول، واتّجاه sipi (ما زال على الافتراض الموروث «الأدنى أسوأ»).
# • القيمة الأدنى = أسوأ: الغطاء النباتيّ/اليخضور/الرطوبة/المياه وTCI/VHI (عالٍ = صحّيّ).
#
# truecolor/et_inputs ليست مؤشّراً قياسيّاً بقيمة واحدة فلا اتّجاه لها. نسخة الحدود
# raster_api_models.canonical_change_index تطابق canonical_index (مفروض باختبار) — الوحدتان
# ورقتان تُحمَّلان بمساريهما فلا تستورد إحداهما الأخرى (ولا تحمل نسخة الحدود اتّجاهاً).
_HIGHER_IS_WORSE = {"salinity", "ndsi", "msi", "cwsi", "tvdi"}
_CONTEXT_DEPENDENT = {"bsi", "bi", "bi2", "dbsi", "ndti", "lst"}
_LOWER_IS_WORSE = {
    "ndvi", "evi", "savi", "ndwi", "ndmi", "gndvi", "fapar", "vari", "gli", "tgi",
    "ndre", "reci", "gci", "arvi", "sipi", "nbr", "ccci", "msavi", "moisture",
    "satvi", "tci", "vhi",
}  # fmt: skip
_DIRECTION_WITHHELD_REASON = "index_direction_context_dependent"
_INDEX_ALIASES = {
    "salt": "salinity",
    "soil_salinity": "salinity",
    "ndvu": "ndvi",
    "vegetation": "ndvi",
}


def canonical_index(index: str | None) -> str:
    """يطبّع اسم المؤشّر (حالة الأحرف/مسافات/شرطات/أسماء بديلة) ويتحقّق منه.

    يرفع ValueError («unknown_change_index») لاسم خارج القائمة المعروفة.
    """
    key = str(index or "").strip().lower().replace(" ", "_").replace("-", "_")
    key = _INDEX_ALIASES.get(key, key)
    if key not in _HIGHER_IS_WORSE | _LOWER_IS_WORSE | _CONTEXT_DEPENDENT:
        raise ValueError(f"unknown_change_index: {index!r}")
    return key


def index_direction(index: str) -> str:
    """اتّجاه المؤشّر الصريح بعد التطبيع: higher_is_worse | lower_is_worse | context_dependent."""
    key = canonical_index(index)
    if key in _HIGHER_IS_WORSE:
        return "higher_is_worse"
    if key in _CONTEXT_DEPENDENT:
        return "context_dependent"
    return "lower_is_worse"


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
    if index in _CONTEXT_DEPENDENT:
        parts.append(
            f"فرق المؤشّر محسوب (متوسّط {mean_delta:+.3f})، لكن لا حكم عامّ بالتحسّن أو التدهور: "
            f"اتّجاه {index} يتبع السياق (حراثة/حصاد/موسم مقابل تدهور غطاء) — "
            "فسِّر خريطة الفرق مع مرحلة المحصول والعمليّات الميدانيّة"
        )
        msg = "؛ ".join(parts) + "."
        if cloud_warning:
            msg += f" ⚠️ التغطية {round(coverage * 100, 1)}% فقط — نتيجة جزئيّة (غيوم/فجوات)."
        return msg
    salinity = index in {"salinity", "ndsi"}  # لا «زحف ملوحة» لإجهاد msi/cwsi/tvdi
    if degraded_pct >= 5.0:
        lead = "زحف ملوحة محتمل: " if salinity else ""
        parts.append(
            f"{lead}تدهور {degraded_pct}% من البكسلات المرصودة المشتركة ({severe_pct}% من البكسلات نفسها بشدّة)"
        )
        # الرؤية الأساسيّة: المتوسّط يبدو سليماً بينما رقعة تدهورت بشدّة.
        if abs(mean_delta) < 0.1 and severe_pct >= 10.0:
            parts.append(
                f"المتوسّط ({mean_delta:+.3f}) يبدو مستقرّاً، لكنّ التدهور موضعيّ "
                "يُخفيه المتوسّط — راجع خريطة الفرق لتحديد الرقعة"
            )
    if improved_pct >= 5.0:
        parts.append(f"تحسّن {improved_pct}% من البكسلات المرصودة المشتركة")
    if not parts:
        parts.append("لا تغيّر مكانيّ ملموس بين التاريخين (المساحة المرصودة مستقرة)")
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

    index = canonical_index(index)
    rows, cols = (int(b.shape[0]), int(b.shape[1])) if b.size else (0, 0)
    total = rows * cols
    higher_is_worse = index in _HIGHER_IS_WORSE
    verdict_withheld = index in _CONTEXT_DEPENDENT
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
    # S3-a: بلا خليّة صالحة مشتركة لا مقارنة أصلاً ⇒ not_assessable ومقاييس null
    # (لا mean_delta=0 ولا نسب 0% تُقرأ «استقراراً مرصوداً»). الشبكتان تبقيان null.
    assessable = valid > 0
    interpretation = _interpret_ar(
        index, coverage, mean_delta, severe_pct, degraded_pct, improved_pct, cloud_warning
    )

    if verdict_withheld:
        # اتّجاه يتبع السياق: فرق البكسل وإحصاؤه حقيقيّان ويُعادان؛ وسم التحسّن/التدهور
        # (change_grid/zones/النسب) يُحجَب بدل تخمينه. changed_pct = |Δ| ≥ العتبة الطفيفة.
        changed_pct = round(100.0 - stable_pct, 2) if assessable else None
        return {
            "index": index,
            "direction": "context_dependent",
            "status": "assessed" if assessable else "not_assessable",
            "reason_codes": [] if assessable else ["no_common_valid_pixels"],
            "verdict_withheld": True,
            "verdict_reason_codes": [_DIRECTION_WITHHELD_REASON],
            "rows": rows,
            "cols": cols,
            "delta_grid": delta_grid,
            "change_grid": None,
            "mean_delta": mean_delta if assessable else None,
            "improved_pct": None,
            "degraded_pct": None,
            "stable_pct": stable_pct if assessable else None,
            "changed_pct": changed_pct,
            "stats": stats if assessable else None,
            "coverage_pct": round(coverage * 100, 2),
            "valid_pixels": valid,
            "percentage_denominator": "common_valid_pixels",
            "degraded_grid_pct": None,
            "total_pixels": total,
            "areas": None,
            "zones": [],
            "thresholds": {"slight": slight, "severe": severe},
            "cloud_warning": cloud_warning,
            "interpretation_ar": interpretation,
        }

    return {
        "index": index,
        "direction": "higher_is_worse" if higher_is_worse else "lower_is_worse",
        "verdict_withheld": False,
        "status": "assessed" if assessable else "not_assessable",
        "reason_codes": [] if assessable else ["no_common_valid_pixels"],
        "rows": rows,
        "cols": cols,
        "delta_grid": delta_grid,  # after - before (None للفجوات)
        "change_grid": code_grid,  # -2/-1/0/1 (None للفجوات) للموبايل
        # مفاتيح مختصرة على المستوى الأعلى (يستهلكها العميل/الموبايل مباشرة)
        "mean_delta": mean_delta if assessable else None,
        "improved_pct": improved_pct if assessable else None,
        "degraded_pct": degraded_pct if assessable else None,
        "stable_pct": stable_pct if assessable else None,
        "stats": stats if assessable else None,
        "coverage_pct": round(coverage * 100, 2),
        "valid_pixels": valid,
        "percentage_denominator": "common_valid_pixels",
        "degraded_grid_pct": round(degraded_pct * coverage, 2) if assessable else None,
        "total_pixels": total,
        "areas": {
            "severe_degraded_pct": severe_pct,
            "degraded_pct": degraded_pct,
            "improved_pct": improved_pct,
            "stable_pct": stable_pct,
        }
        if assessable
        else None,
        "zones": _zones_from_codes(code_grid, delta_grid, rows, cols),
        "thresholds": {"slight": slight, "severe": severe},
        "cloud_warning": cloud_warning,
        "interpretation_ar": interpretation,
    }
