"""
sahool_core.engines.deficit_irrigation
=======================================
مقايضة عجز الري ↔ الملوحة — أهمّ توازن في الزراعة اليمنية الجافة.

المعضلة (مؤكَّدة بالأدبيات 2025):
  • عجز الري يوفّر الماء النادر ويرفع كفاءة استخدامه (WUE).
    الريّ بـ90% ETc يعطي أعلى كفاءة مائية (Frontiers 2021).
  • لكن العجز الحادّ يقلّل الغسل → تتراكم الأملاح (الوثائق: العجز
    الحادّ يزيد خطر الملوحة في المناطق الجافة بتقليل الغسل).
  • المفارقة: عجز معتدل (~80-90%) قد يقلّل الملوحة بتقليل صعود
    الماء المالح؛ لكن عجز شديد (40-60% طويل الأمد) يراكمها.

أرقام الأدبيات (Nature Sci Rep 2025، شبه جافة):
  خفض الغلّة مقابل I100: 80%ETc→7%، 60%→23%، 40%→50%.
  أي: عجز معتدل (80%) خفض غلّة مقبول (7%)، عجز حادّ (40%) كارثي (50%).

المبدأ: لا "توصية عجز" دون حساب أثر الملوحة. النواة تكشف المقايضة
صراحةً، ولا توصي بعجز حادّ إن كان ماء الري مالحاً (يراكم الأملاح).
تتّكئ على fao56.leaching_requirement الموجود. سقف MEDIUM (تقديري).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# خفض الغلّة التقريبي مقابل نسبة ETc (Nature Sci Rep 2025, شبه جاف)
_YIELD_PENALTY = {100: 0.0, 90: 0.04, 80: 0.07, 70: 0.15, 60: 0.23, 40: 0.50}


@dataclass
class DeficitTradeoff:
    etc_fraction: int                 # نسبة الري المطبّق (% من ETc)
    yield_penalty_pct: float          # خفض الغلّة المتوقّع
    salinity_risk: str                # low / medium / high
    wue_gain: bool                    # هل يحسّن كفاءة الماء؟
    recommended: bool
    confidence: str
    warnings_ar: list[str] = field(default_factory=list)
    note_ar: str = ""


def _interp_penalty(frac: int) -> float:
    """خفض الغلّة بالاستيفاء الخطّي بين نقاط الأدبيات."""
    keys = sorted(_YIELD_PENALTY)
    if frac >= 100:
        return 0.0
    if frac <= 40:
        return _YIELD_PENALTY[40]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= frac <= hi:
            t = (frac - lo) / (hi - lo)
            return round(_YIELD_PENALTY[lo] + t * (_YIELD_PENALTY[hi] - _YIELD_PENALTY[lo]), 3)
    return 0.0


def evaluate_deficit_irrigation(
    *,
    etc_fraction: int,
    water_ec_ds_m: float | None,
    crop_salinity_threshold_ds_m: float | None,
    season_length_days: int = 120,
    is_irrigated: bool = True,
) -> DeficitTradeoff:
    """يقيّم مقايضة عجز الري: توفير الماء مقابل تراكم الملح.

    الحاسم: إن كان ماء الري مالحاً، العجز الحادّ يراكم الأملاح (تقليل الغسل)
    → لا يُوصى به مهما وفّر الماء. الفيزياء (الملوحة حاكم) تَغلِب التوفير.

    حارس السياق (تصحيح بعد مراجعة): هذا المحرّك يخصّ المناطق المرويّة فقط
    (محوري/تنقيط/غمر) — حيث "عجز الريّ" قرار إداري. لا ينطبق على الزراعة
    المطرية (rainfed) حيث المطر يحدّد الماء لا المزارع؛ هناك يُستخدم الريّ
    التكميلي (مفهوم مختلف). is_irrigated=False → لا توصية عجز."""
    if not is_irrigated:
        return DeficitTradeoff(
            etc_fraction=etc_fraction, yield_penalty_pct=0.0,
            salinity_risk="low", wue_gain=False, recommended=False,
            confidence="none",
            warnings_ar=["هذا المحرّك للمناطق المرويّة لا المطرية — "
                         "في الزراعة المطرية يُدار الماء بالريّ التكميلي لا بعجز الريّ"],
            note_ar="غير منطبق: الحقل مطريّ (لا مرويّ). عجز الريّ قرار إداري "
                    "يخصّ المناطق المرويّة فقط.")
    penalty = _interp_penalty(etc_fraction)
    warnings: list[str] = []

    # تقييم خطر الملوحة من العجز
    salt_risk = "low"
    if water_ec_ds_m is not None and crop_salinity_threshold_ds_m is not None:
        # ماء مالح + عجز = خطر تراكم (الغسل يقلّ مع العجز)
        ec_ratio = water_ec_ds_m / max(crop_salinity_threshold_ds_m, 0.1)
        if etc_fraction < 70 and ec_ratio > 0.5:
            salt_risk = "high"
            warnings.append(
                f"⚠️ ماء الري مالح (EC={water_ec_ds_m}) + عجز حادّ ({etc_fraction}% ETc) "
                "= تراكم أملاح خطير (الغسل يقلّ). الفيزياء ترفض هذا المزيج.")
        elif etc_fraction < 80 and ec_ratio > 0.3:
            salt_risk = "medium"
            warnings.append(
                "عجز متوسّط مع ماء مالح — راقب ملوحة التربة؛ قد تحتاج ريّة غسل دورية")
    elif water_ec_ds_m is None:
        warnings.append("ملوحة ماء الري غير معروفة — لا يمكن تقييم خطر تراكم الأملاح بثقة")

    # WUE: العجز المعتدل (80-90%) يحسّن الكفاءة؛ الحادّ لا
    wue_gain = 80 <= etc_fraction < 100

    # القرار
    recommended = False
    if salt_risk == "high":
        note = f"عجز {etc_fraction}% غير مُوصى به — خطر تراكم أملاح يفوق توفير الماء"
    elif penalty > 0.20:
        note = f"عجز {etc_fraction}% يخفض الغلّة ~{penalty:.0%} — حادّ، استشر خبيراً"
    elif 80 <= etc_fraction <= 90 and salt_risk == "low":
        recommended = True
        note = (f"عجز معتدل ({etc_fraction}%) خيار جيد — يوفّر الماء، خفض غلّة "
                f"~{penalty:.0%}, كفاءة أعلى")
    else:
        note = f"عجز {etc_fraction}% — خفض غلّة ~{penalty:.0%}؛ وازِن التوفير بالخسارة"

    warnings.append("تقديري (سقف متوسّط) — معايَر على دراسات شبه جافة، لا حقلك تحديداً")
    return DeficitTradeoff(
        etc_fraction=etc_fraction, yield_penalty_pct=round(penalty, 3),
        salinity_risk=salt_risk, wue_gain=wue_gain, recommended=recommended,
        confidence="medium" if salt_risk != "high" else "low",
        warnings_ar=warnings, note_ar=note)


def soc_water_capacity_gain(soc_increase_pct: float, soil_depth_cm: float = 30.0) -> dict:
    """أثر زيادة الكربون العضوي على السعة المائية المتاحة.

    رقم الأدبيات (MU Extension/Hudson): 1% SOC يرفع الماء المتاح
    1.5-2.5 مم لكل 30سم عمق. حلّ مباشر للجفاف في التربة الخشنة."""
    low = soc_increase_pct * 1.5 * (soil_depth_cm / 30.0)
    high = soc_increase_pct * 2.5 * (soil_depth_cm / 30.0)
    return {
        "awc_gain_mm_low": round(low, 2),
        "awc_gain_mm_high": round(high, 2),
        "note_ar": (f"زيادة {soc_increase_pct}% كربون عضوي ترفع الماء المتاح "
                    f"~{low:.1f}-{high:.1f}مم/{soil_depth_cm:.0f}سم — "
                    "أثر تراكمي بطيء (مواسم)، يحسّن مقاومة الجفاف"),
        "confidence": "medium",
    }
