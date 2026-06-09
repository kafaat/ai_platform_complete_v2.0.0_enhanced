"""
sahool_core.engines.planting_window
====================================
موعد الزراعة الأمثل — يحسب متى تُزرع كي يقع الإزهار في فترة أبرد
(تجنّب الإجهاد الحراري عند الإزهار، أكبر مخفِّض للغلّة في الحبوب).

ممارسة فيزيائية-مجتمعية: GDD (فيزياء) + خبرة المزارع (متى يزرع الناس).
لا تحتاج مختبراً — تعتمد على الطقس وGDD ومراقبة الإزهار.

الأساس الفيزيائي:
  إذا تجاوزت حرارة الإزهار عتبة حرجة (قمح ~31°م) → عقم اللقاح → انخفاض الغلّة.
  الحلّ: ضبط موعد الزراعة كي يقع الإزهار (عند GDD معيّن) في نافذة أبرد.

المقايضة المخفية (تحذير إلزامي — الوثيقة محقّة):
  تقديم الزراعة يتجنّب الحرارة لكنه قد يُعرّض الأزهار للصقيع المتأخر.
  كل تعديل موعد يحلّ مشكلة ويُنشئ أخرى. النواة تحسب المخاطر المركّبة.

الصدق: السقف MEDIUM لا HIGH — الطقس متوقّع لا مضمون. والتحيّز الناجي
("نجح بعض المزارعين") لا يعني "الأفضل" — نعرضه "خياراً مجرّباً" لا "الأمثل".
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlantingWindowResult:
    safe_window_found: bool
    recommended_sowing_offset_days: int | None  # إزاحة عن تاريخ مرجعي
    flowering_max_temp_c: float | None
    confidence: str                  # medium / low
    frost_risk: bool
    warnings_ar: list[str] = field(default_factory=list)
    note_ar: str = ""


def days_to_accumulate_gdd(target_gdd: float, daily_gdd: list[float]) -> int | None:
    """عدد الأيام لبلوغ GDD مستهدف من سلسلة GDD يومية. None إن لم يُبلغ."""
    cumulative = 0.0
    for i, g in enumerate(daily_gdd):
        cumulative += g
        if cumulative >= target_gdd:
            return i + 1
    return None


def find_planting_window(
    *,
    flowering_gdd: float,
    daily_gdd_by_sowing: dict[int, list[float]],     # offset → سلسلة GDD
    daily_tmax_by_sowing: dict[int, list[float]],    # offset → سلسلة tmax
    heat_threshold_c: float,
    frost_risk_offset_days: int | None = None,       # آخر تاريخ صقيع (إزاحة)
    flowering_window_days: int = 10,
) -> PlantingWindowResult:
    """يبحث عن موعد زراعة يقع الإزهار فيه تحت عتبة الحرارة.

    لكل موعد مرشّح: يحسب يوم الإزهار (ببلوغ flowering_gdd)، ثم أقصى حرارة
    في نافذة الإزهار. أوّل موعد آمن (تحت العتبة) يُرجَع — مع تحذير الصقيع."""
    candidates = sorted(daily_gdd_by_sowing.keys())
    best = None
    for offset in candidates:
        gdd_series = daily_gdd_by_sowing[offset]
        tmax_series = daily_tmax_by_sowing.get(offset, [])
        flower_day = days_to_accumulate_gdd(flowering_gdd, gdd_series)
        if flower_day is None:
            continue  # لا يبلغ الإزهار في الأفق المتاح
        window = tmax_series[flower_day: flower_day + flowering_window_days]
        if not window:
            continue
        max_t = max(window)
        if max_t < heat_threshold_c:
            best = (offset, max_t)
            break  # أوّل موعد آمن

    if best is None:
        return PlantingWindowResult(
            safe_window_found=False, recommended_sowing_offset_days=None,
            flowering_max_temp_c=None, confidence="low", frost_risk=False,
            note_ar="لا نافذة زراعة آمنة من الإجهاد الحراري في الأفق المتاح — "
                    "استشر خبيراً أو فكّر بمحصول أكثر تحمّلاً للحرارة")

    offset, max_t = best
    warnings = [
        "هذا خيار مجرّب لا «الأمثل» — مبني على خبرة بعض المزارعين والطقس المتوقّع",
        "الطقس متوقّع لا مضمون؛ راقب التوقّعات قرب الإزهار",
    ]
    frost = False
    # المقايضة المخفية: تقديم كبير قبل آخر صقيع → خطر صقيع
    if frost_risk_offset_days is not None and offset < frost_risk_offset_days:
        frost = True
        warnings.append(
            f"⚠️ تحذير المقايضة: هذا الموعد ({offset} يوم) يسبق آخر صقيع متوقّع "
            f"({frost_risk_offset_days} يوم) — تجنّب الحرارة يُنشئ خطر الصقيع. "
            "وازِن بين الخطرين أو أخّر قليلاً.")

    return PlantingWindowResult(
        safe_window_found=True, recommended_sowing_offset_days=offset,
        flowering_max_temp_c=round(max_t, 1),
        confidence="medium",   # سقف MEDIUM: الطقس متوقّع
        frost_risk=frost, warnings_ar=warnings,
        note_ar=f"موعد مرشّح: إزاحة {offset} يوم — يقع الإزهار تحت "
                f"{heat_threshold_c}°م (أقصى متوقّع {round(max_t,1)}°م)")
