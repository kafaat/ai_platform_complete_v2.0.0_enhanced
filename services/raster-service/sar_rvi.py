"""
sar_rvi.py — مؤشّر الغطاء الراداري (Radar Vegetation Index) من Sentinel-1 VV/VH.

يُكمل مقاومة السحاب: fuse_health يرفع وزن العائلة "sar" عند السحاب، لكنّه يحتاج
قيمة رادارية مُطبَّعة [0,1] (لا backscatter خام بـdB لا يُدمَج مع NDVI). هذا
الملفّ يحسب RVI ثنائي الاستقطاب فعليّاً من Sentinel-1 GRD المُعايَر.

الصيغة (dual-pol RVI):
    RVI = 4 · σ°_VH / (σ°_VV + σ°_VH)        [بقدرة خطّيّة linear power]

  • تشتّت سطحي (تربة عارية): VH ≪ VV ⇒ RVI → 0
  • تشتّت حجمي (غطاء كثيف): VH ≈ VV ⇒ RVI يقترب من 2
نقصّه إلى [0,1] لاستخدامه كبديل غطاء نباتيّ قابل للدمج مع NDVI (الكثيف يتشبّع
عند 1). إن كانت المدخلات بـdB (شائع بعد المعايرة) تُحوَّل للخطّي أوّلاً:
    linear = 10^(dB/10)

نقيّ (numpy فقط، لا I/O) وحتميّ. NaN/None و(VV+VH ≤ 0) ⇒ NaN (لا تُفبرَك قيمة).
"""

from __future__ import annotations


def _to_arr(grid):
    import numpy as np

    if hasattr(grid, "shape"):
        return np.asarray(grid, dtype="float64")
    return np.array(
        [[float("nan") if v is None else float(v) for v in row] for row in grid],
        dtype="float64",
    )


def rvi_from_vv_vh(vv, vh, *, in_db: bool = False):
    """يحسب مصفوفة RVI ثنائيّة من VV/VH (numpy). يقصّ إلى [0,1] كبديل غطاء.

    in_db: إن كانت القيم بالديسيبل تُحوَّل للقدرة الخطّيّة قبل النسبة.
    يرفع ValueError إن اختلفت أبعاد VV/VH.
    """
    import numpy as np

    a_vv = _to_arr(vv)
    a_vh = _to_arr(vh)
    if a_vv.shape != a_vh.shape:
        raise ValueError(f"شكل VV/VH مختلف: vv={a_vv.shape} vh={a_vh.shape}")
    if in_db:
        a_vv = np.power(10.0, a_vv / 10.0)
        a_vh = np.power(10.0, a_vh / 10.0)
    denom = a_vv + a_vh
    with np.errstate(invalid="ignore", divide="ignore"):
        rvi = 4.0 * a_vh / denom
    rvi = np.where(np.isfinite(rvi) & (denom > 0), rvi, np.nan)
    return np.clip(rvi, 0.0, 1.0)


def compute_rvi(vv_grid, vh_grid, *, in_db: bool = False) -> dict:
    """يحسب شبكة RVI + المتوسّط + التغطية من شبكتي VV/VH (نفس الأبعاد).

    Returns dict: rvi_grid (None للفجوات) + rvi_mean + التغطية + note عند غياب
    بكسلات صالحة. rvi_mean جاهز للتمرير كإشارة source="rvi" (family="sar").
    """
    import numpy as np

    rvi = rvi_from_vv_vh(vv_grid, vh_grid, in_db=in_db)
    if rvi.ndim != 2:
        raise ValueError("VV/VH يجب أن تكونا شبكتين ثنائيّتي الأبعاد")
    rows, cols = (int(rvi.shape[0]), int(rvi.shape[1])) if rvi.size else (0, 0)
    total = rows * cols
    finite = rvi[np.isfinite(rvi)]
    valid = int(finite.size)
    grid = [[None if not np.isfinite(v) else round(float(v), 4) for v in row] for row in rvi]
    return {
        "rvi_grid": grid,
        "rvi_mean": round(float(finite.mean()), 4) if valid else 0.0,
        "rows": rows,
        "cols": cols,
        "valid_pixels": valid,
        "total_pixels": total,
        "coverage_pct": round(100.0 * valid / total, 2) if total else 0.0,
        "in_db": in_db,
        "note": None if valid else "لا بكسلات صالحة (VV/VH مفقودان أو VV+VH ≤ 0)",
    }
