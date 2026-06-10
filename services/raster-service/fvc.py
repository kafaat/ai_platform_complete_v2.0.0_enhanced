"""
fvc.py — Fractional Vegetation Cover (نسبة التغطية النباتيّة) عبر نموذج البكسل
الثنائي (Dimidiate Pixel Model).

الفجوة المُسدَّة: النظام يحسب LAI (مؤشّر مساحة الورقة، بُعد 3D عبر Beer-Lambert في
vegetation-analysis-service) لكن ليس FVC (نسبة تغطية الأرض، بُعد 2D). مختلفان
ومكمّلان: LAI يقيس كثافة الأوراق، FVC يقيس أيّ نسبة من الأرض يغطّيها النبات. FVC
أساس موضوعي لرصد زحف التصحّر وتغطية المحاصيل عبر مراحل النموّ — حرجٌ للجوف.

الصيغة (Dimidiate Pixel Model):
    FVC = (NDVI − NDVI_soil) / (NDVI_veg − NDVI_soil)، مقصوصة إلى [0, 1]

تحديد القيم الطرفيّة (endmembers) — ثلاث طرق:
  • cumulative_frequency (موصى): مئين 5% = تربة، 95% = نبات (يتكيّف إقليميّاً).
  • global_constant: 0.05/0.80 (واسع النطاق، بلا معايرة).
  • dynamic_range: قيمتان مُمرَّرتان (لسلسلة زمنيّة بقيم ثابتة مُعايَرة).

نقيّة (numpy فقط، لا I/O) وحتميّة. NaN/None (غيوم/خارج الحقل) محفوظة ولا يُفبرَك
عبرها غطاء. على حقل موحّد بالكامل (تباين NDVI ضئيل) القيم الطرفيّة تتقارب —
تُرجَع note صريحة وتُعتبر النتيجة غير موثوقة بدل القسمة على صفر.
"""

from __future__ import annotations

_DESERT_BELOW = 0.3  # FVC < 0.3 ⇒ تغطية منخفضة / تصحّر
_HIGH_ABOVE = 0.6  # FVC > 0.6 ⇒ تغطية عالية
_COVERAGE_WARN_BELOW = 0.6  # تغطية صالحة دونها النتيجة جزئيّة (غيوم/فجوات)
_MIN_CONTRAST = 1e-3  # أدنى فرق (veg − soil) يُعتبر موثوقاً

_VALID_METHODS = ("cumulative_frequency", "global_constant", "dynamic_range")


def _to_float_array(grid):
    """يحوّل شبكة list[list[float|None]] (أو numpy) إلى numpy float بـNaN للفجوات."""
    import numpy as np

    if hasattr(grid, "shape"):
        return np.asarray(grid, dtype="float64")
    return np.array(
        [[float("nan") if v is None else float(v) for v in row] for row in grid],
        dtype="float64",
    )


def _endmembers(finite, method, ndvi_soil, ndvi_veg, _np):
    """يحدّد (NDVI_soil, NDVI_veg) حسب الطريقة المختارة."""
    if method == "global_constant":
        return 0.05, 0.80
    if method == "dynamic_range":
        if ndvi_soil is None or ndvi_veg is None:
            raise ValueError("dynamic_range يتطلّب تمرير ndvi_soil و ndvi_veg")
        return float(ndvi_soil), float(ndvi_veg)
    # cumulative_frequency (الافتراضي): المئين 5% و 95% (يتكيّف إقليميّاً)
    if finite.size == 0:
        return 0.05, 0.80
    return float(_np.percentile(finite, 5)), float(_np.percentile(finite, 95))


def _interpret_ar(mean_fvc, desert_pct, high_pct, cloud_warning, coverage, note):
    """تفسير عربي موجز لنسبة التغطية وتصنيفها."""
    if coverage <= 0.0:
        return "لا بكسلات صالحة لحساب التغطية (تغطية صفر — غيوم/فجوات)."
    pct = round(mean_fvc * 100)
    if mean_fvc < _DESERT_BELOW:
        head = f"تغطية نباتيّة منخفضة (وسطى {pct}%) — مؤشّر تصحّر/أرض شبه عارية"
    elif mean_fvc > _HIGH_ABOVE:
        head = f"تغطية نباتيّة عالية (وسطى {pct}%)"
    else:
        head = f"تغطية نباتيّة متوسّطة (وسطى {pct}%)"
    parts = [head]
    if desert_pct >= 5.0:
        parts.append(f"{desert_pct}% من الحقل تغطيته منخفضة (تصحّر محتمل)")
    msg = "؛ ".join(parts) + "."
    if note:
        msg += f" ⚠️ {note}."
    if cloud_warning:
        msg += f" ⚠️ التغطية {round(coverage * 100, 1)}% فقط — نتيجة جزئيّة."
    return msg


def compute_fvc(
    ndvi,
    *,
    method: str = "cumulative_frequency",
    ndvi_soil: float | None = None,
    ndvi_veg: float | None = None,
) -> dict:
    """يحسب نسبة التغطية النباتيّة (FVC) من شبكة NDVI عبر نموذج البكسل الثنائي.

    Parameters
    ----------
    ndvi:
        شبكة NDVI (list[list[float|None]] أو numpy). None/NaN = فجوة (غيمة/خارج
        الحقل) — تُحفظ ولا يُحسب غطاء عبرها.
    method:
        cumulative_frequency | global_constant | dynamic_range.
    ndvi_soil, ndvi_veg:
        القيمتان الطرفيّتان (مطلوبتان فقط لـdynamic_range).

    Returns
    -------
    dict
        fvc_grid + إحصاءات + نسب التصحّر/التغطية العالية + تصنيف + تفسير عربي.
        يرفع ValueError لطريقة غير معروفة أو dynamic_range بلا قيم.
    """
    import numpy as np

    if method not in _VALID_METHODS:
        raise ValueError(f"طريقة غير معروفة: {method!r}. المسموح: {', '.join(_VALID_METHODS)}")

    a = _to_float_array(ndvi)
    if a.ndim != 2:
        raise ValueError("شبكة NDVI يجب أن تكون ثنائيّة الأبعاد (rows×cols)")
    rows, cols = (int(a.shape[0]), int(a.shape[1])) if a.size else (0, 0)
    total = rows * cols

    finite = a[np.isfinite(a)]
    soil_v, veg_v = _endmembers(finite, method, ndvi_soil, ndvi_veg, np)

    note = None
    denom = veg_v - soil_v
    if denom <= _MIN_CONTRAST:
        # تباين ضئيل: لا يمكن فصل التربة عن النبات بثقة (حقل موحّد؟).
        note = "تباين NDVI ضئيل (قيم طرفيّة متقاربة) — FVC غير موثوق"
        denom = _MIN_CONTRAST  # نتجنّب القسمة على صفر؛ النتيجة ستتشبّع

    fvc = np.clip((a - soil_v) / denom, 0.0, 1.0)
    fvc = np.where(np.isfinite(a), fvc, np.nan)  # حفظ الفجوات (صدق السحاب)

    fvc_grid = [[None if not np.isfinite(v) else round(float(v), 4) for v in row] for row in fvc]

    valid = int(np.isfinite(fvc).sum())
    coverage = (valid / total) if total else 0.0
    finite_fvc = fvc[np.isfinite(fvc)]
    if finite_fvc.size:
        mean_fvc = round(float(finite_fvc.mean()), 4)
        stats = {
            "min": round(float(finite_fvc.min()), 4),
            "max": round(float(finite_fvc.max()), 4),
            "mean": mean_fvc,
        }
        desert_pct = round(100.0 * int(np.sum(finite_fvc < _DESERT_BELOW)) / valid, 2)
        high_pct = round(100.0 * int(np.sum(finite_fvc > _HIGH_ABOVE)) / valid, 2)
    else:
        mean_fvc = 0.0
        stats = {"min": 0.0, "max": 0.0, "mean": 0.0}
        desert_pct = high_pct = 0.0

    if mean_fvc < _DESERT_BELOW:
        classification = "low_cover"
    elif mean_fvc > _HIGH_ABOVE:
        classification = "high_cover"
    else:
        classification = "moderate_cover"
    cloud_warning = coverage < _COVERAGE_WARN_BELOW

    return {
        "method": method,
        "ndvi_soil": round(soil_v, 4),
        "ndvi_veg": round(veg_v, 4),
        "rows": rows,
        "cols": cols,
        "fvc_grid": fvc_grid,
        "stats": stats,
        "coverage_pct": round(coverage * 100, 2),
        "valid_pixels": valid,
        "total_pixels": total,
        "areas": {"desertification_pct": desert_pct, "high_cover_pct": high_pct},
        "classification": classification,
        "cloud_warning": cloud_warning,
        "note": note,
        "interpretation_ar": _interpret_ar(
            mean_fvc, desert_pct, high_pct, cloud_warning, coverage, note
        ),
    }
