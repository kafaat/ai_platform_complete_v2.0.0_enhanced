"""
management_zones.py — مناطق الإدارة داخل الحقل (سدّ فجوة P1).

الممارسة العالميّة (الزراعة الدقيقة): تقسيم الحقل إلى مناطق أداء (عالٍ/متوسّط/
منخفض) بناءً على ثبات المؤشّر عبر الزمن، ثمّ توجيه المدخلات (سماد/ريّ) لكلّ
منطقة — أساس الوصفات متغيّرة المعدّل (VRT). يقلّل الكلفة ويحسّن الغلّة.

يعمل على إحصاءات/قيم المؤشّر (لا يحتاج مكتبات ثقيلة). التقسيم بالكوانتايل
(quantile) على متوسّط المؤشّر، مع علامة ثبات (CV عبر الزمن).
"""

from __future__ import annotations

import statistics


def classify_zones(
    pixel_values: list[float],
    n_zones: int = 3,
) -> dict:
    """يقسّم قيم بكسلات الحقل إلى n مناطق أداء بالكوانتايل.

    3 مناطق افتراضيّة: منخفض/متوسّط/عالٍ. الكوانتايل أمتن من العتبات الثابتة
    (يتكيّف مع توزيع الحقل الفعلي). صدق: يحتاج قيماً حقيقيّة، لا يخترعها.
    """
    vals = [v for v in pixel_values if v is not None and _finite(v)]
    if len(vals) < n_zones:
        return {"zones": [], "error": "قيم غير كافية للتقسيم", "pixels": len(vals)}

    vals_sorted = sorted(vals)
    # حدود الكوانتايل
    cuts = [vals_sorted[int(len(vals_sorted) * i / n_zones)] for i in range(1, n_zones)]
    labels = (
        ["low", "medium", "high"] if n_zones == 3 else [f"zone_{i + 1}" for i in range(n_zones)]
    )

    counts = [0] * n_zones
    for v in vals:
        z = 0
        for c in cuts:
            if v >= c:
                z += 1
        counts[z] += 1

    total = len(vals)
    zones = []
    for i in range(n_zones):
        zones.append(
            {
                "zone": labels[i] if i < len(labels) else f"zone_{i + 1}",
                "pixel_count": counts[i],
                "pct": round(100 * counts[i] / total, 1),
                "value_range": [
                    round(vals_sorted[0] if i == 0 else cuts[i - 1], 4),
                    round(cuts[i] if i < len(cuts) else vals_sorted[-1], 4),
                ],
            }
        )
    return {
        "n_zones": n_zones,
        "total_pixels": total,
        "zones": zones,
        "field_mean": round(statistics.fmean(vals), 4),
        "field_cv": round(statistics.pstdev(vals) / statistics.fmean(vals), 3)
        if statistics.fmean(vals)
        else None,
    }


def stability_zones(
    temporal_values: list[list[float]],
) -> dict:
    """مناطق الثبات: يجمع عدّة تواريخ ليحدّد المناطق الثابتة عبر الزمن.

    المدخل: قائمة [تاريخ][بكسل]. المخرج: لكلّ بكسل، المتوسّط + معامل التباين
    (CV) عبر الزمن. CV منخفض = ثابت (موثوق للإدارة)؛ عالٍ = غير مستقرّ.
    هذا يطابق منهجيّة "yield stability zones" في الأدبيّات.
    """
    if not temporal_values or len(temporal_values) < 2:
        return {"error": "يحتاج تاريخين على الأقلّ للثبات", "dates": len(temporal_values)}

    n_px = min(len(t) for t in temporal_values)
    stable, unstable = 0, 0
    means = []
    for px in range(n_px):
        series = [
            temporal_values[t][px]
            for t in range(len(temporal_values))
            if _finite(temporal_values[t][px])
        ]
        if len(series) < 2:
            continue
        m = statistics.fmean(series)
        cv = statistics.pstdev(series) / m if m else 1.0
        means.append(m)
        if cv <= 0.15:  # CV ≤ 15% = ثابت (عتبة معياريّة)
            stable += 1
        else:
            unstable += 1
    total = stable + unstable
    return {
        "dates": len(temporal_values),
        "pixels_analyzed": total,
        "stable_pct": round(100 * stable / total, 1) if total else 0,
        "unstable_pct": round(100 * unstable / total, 1) if total else 0,
        "note": "CV≤15% = منطقة ثابتة موثوقة للإدارة؛ العالية تحتاج تحقّقاً ميدانيّاً",
    }


def prescription_from_zones(
    zones: list[dict],
    base_rate: float,
    strategy: str = "compensate",
) -> list[dict]:
    """وصفة متغيّرة المعدّل (VRT) من المناطق.

    strategy='compensate': المناطق الضعيفة تأخذ أكثر (تعويض) — شائع للسماد.
    strategy='protect': المناطق القويّة تأخذ أكثر (استثمار في المنتج) — بديل.
    صدق: معامِلات إرشاديّة؛ المعدّل النهائي قرار agronomic يحتاج تحقّقاً.
    """
    factors_compensate = {"low": 1.2, "medium": 1.0, "high": 0.8}
    factors_protect = {"low": 0.8, "medium": 1.0, "high": 1.2}
    factors = factors_compensate if strategy == "compensate" else factors_protect

    out = []
    for z in zones:
        zone = z.get("zone", "medium")
        factor = factors.get(zone, 1.0)
        out.append(
            {
                "zone": zone,
                "pct_of_field": z.get("pct"),
                "rate": round(base_rate * factor, 2),
                "factor": factor,
            }
        )
    return out


def prescription_from_grid(
    grid: list[list],
    n_zones: int = 3,
    base_rate: float | None = None,
    strategy: str = "compensate",
) -> dict:
    """يحوّل شبكة مؤشّر (rows من float|None) إلى مناطق إدارة + وصفة معدّل.

    يسطّح الشبكة (متجاهلاً null/NaN)، يقسّمها بالكوانتايل عبر classify_zones،
    ثمّ يلصق المعدّل الموصى به لكلّ منطقة إن مُرّر base_rate. صدق: يعمل على قيم
    حقيقيّة فقط؛ شبكة فارغة → zones=[] مع خطأ واضح (لا اختراع معدّلات).

    يُرجِع: {n_zones, total_pixels, zones, field_mean, field_cv,
             prescription?: [...]}  حيث كلّ zone يحمل value_range وpct
    وpixel_count، وعند الوصفة rate/factor.
    """
    flat = [v for row in grid for v in row]
    result = classify_zones(flat, n_zones=n_zones)
    if base_rate is not None and result.get("zones"):
        rx = prescription_from_zones(result["zones"], base_rate, strategy=strategy)
        # ادمج المعدّل داخل كلّ منطقة (per-zone stats + rate في كائن واحد)
        rate_by_zone = {r["zone"]: r for r in rx}
        for z in result["zones"]:
            r = rate_by_zone.get(z["zone"])
            if r:
                z["rate"] = r["rate"]
                z["factor"] = r["factor"]
        result["prescription"] = rx
        result["base_rate"] = base_rate
        result["strategy"] = strategy
    return result


def _finite(v) -> bool:
    try:
        return v == v and abs(v) != float("inf")
    except Exception:
        return False
