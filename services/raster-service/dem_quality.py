"""جودة نموذج الارتفاعات من طبقة NUM (عدد المشاهد) — منطق صرف (V63.6).

ASTER GDEM يوزّع طبقتين لكلّ tile: **DEM** (الارتفاع) و**NUM** (عدد المشاهد المساهِمة
في قيمة الخليّة). NUM منخفض ⇒ ثقة أقلّ في الارتفاع. هذا المنطق يحوّل إحصاء NUM إلى
إشارة جودة/ثقة **صادقة** تُرافِق مشتقّات التضاريس (slope/hillshade/contours) — لا اختلاق:
بلا NUM ⇒ ``status="unknown"`` (لا تخمين)، والثقة مُشتقّة من الكثافة والتغطية الدنيا.

نقيّ (بلا rasterio/I/O)؛ يستقبل قيم NUM المقروءة من المستورِد ويُرجِع تقييماً حتميّاً.
"""

from __future__ import annotations

import math
from typing import Any

_LOW_OBS_THRESHOLD = 3  # NUM < 3 مشاهد ⇒ خليّة ضعيفة الثقة (اصطلاح ASTER الشائع).
_HIGH_OBS_TARGET = 12.0  # ~12 مشهداً فأكثر ⇒ ثقة كاملة على محور الكثافة.


def _finite_nonneg(values: Any) -> list[float]:
    out: list[float] = []
    for v in values or []:
        if isinstance(v, bool):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f) and f >= 0:
            out.append(f)
    return out


def dem_quality_from_num(
    num_values: Any,
    *,
    low_obs_threshold: int = _LOW_OBS_THRESHOLD,
) -> dict[str, Any]:
    """يحوّل قيم NUM (عدد المشاهد لكلّ خليّة) إلى تقييم جودة/ثقة DEM.

    **صدق:** بلا قيم صالحة ⇒ ``status="unknown"`` (لا تخمين). الثقة =
    (متوسّط المشاهد / الهدف) × (1 − نسبة الخلايا ضعيفة التغطية)، مقصوصة إلى [0,1].
    التصنيف: high (كثافة عالية + تغطية ضعيفة نادرة) · medium · low.
    """
    vals = _finite_nonneg(num_values)
    if not vals:
        return {"status": "unknown", "reason": "no_num_data"}
    n = len(vals)
    mean_obs = sum(vals) / n
    low = sum(1 for v in vals if v < low_obs_threshold)
    low_frac = round(low / n, 4)

    if mean_obs >= 10 and low_frac < 0.05:
        quality = "high"
    elif mean_obs >= 5 and low_frac < 0.20:
        quality = "medium"
    else:
        quality = "low"

    density = min(1.0, mean_obs / _HIGH_OBS_TARGET)
    confidence = round(max(0.0, min(1.0, density * (1.0 - low_frac))), 3)
    return {
        "status": "present",
        "n": n,
        "mean_observations": round(mean_obs, 3),
        "min_observations": round(min(vals), 3),
        "low_coverage_fraction": low_frac,
        "quality": quality,
        "confidence": confidence,
        "note_ar": "ثقة DEM من طبقة NUM (عدد المشاهد)؛ كثافة أعلى وتغطية ضعيفة أقلّ ⇒ ثقة أعلى.",
    }
