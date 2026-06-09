"""
api/trial_engine.py — محرّك تحليل التجارب المقترنة (t-test / LSD)

خارطة الطريق: المرحلة ٢، البند ١١. الميزة الرئيسيّة لـ"الصدق الإحصائي".

يأخذ نتائج حصاد كتل مقترنة (معالجة مقابل مقارنة) ويُجري اختبار t مزدوج +
LSD ليُجيب بصدق: "هل الفرق مؤكّد إحصائيّاً أم مجرّد تباين طبيعي؟"

المعايير العلميّة (SARE / Penn State / Purdue / Iowa State / FAO):
  • مقارنة مقترنة (معالجة مقابل مقارنة)، لا تقسيم الحقل لنصفَين
  • ≥4 كتل مكرّرة (الحدّ الأدنى للصحّة الإحصائيّة)
  • اختبار t مزدوج: t = mean(d) / (sd(d)/√n)
  • LSD = t_critical × SE_diff؛ الفرق مؤكّد لو |mean(d)| > LSD
  • "لا فرق" نتيجة صحيحة وقيّمة — لا نُجمّل

يستخدم scipy.stats لتوزيع t (دقيق). يدمج اختياريّاً معايرة trueup.py للرطوبة.

⚠ لا EONR/Quadratic-Plateau هنا (يحتاج yield-response متعدّد السنوات لا نملكه
— حذّرنا من ثوابت الذرة الأمريكيّة). هذا المحرّك يُنتج البيانات التي قد يحتاجها
EONR لاحقاً، بالترتيب الصحيح.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass
class BlockResult:
    """نتيجة حصاد كتلة واحدة: إنتاج المعالجة مقابل المقارنة."""

    block_number: int
    treatment_yield: float  # kg/ha (أو أيّ وحدة متّسقة)
    control_yield: float


@dataclass
class TrialVerdict:
    """نتيجة التحليل الإحصائي الكاملة."""

    n_blocks: int
    treatment_mean: float
    control_mean: float
    mean_difference: float  # معالجة − مقارنة
    std_diff: float
    se_diff: float
    t_statistic: float
    df: int
    p_value: float
    confidence_level: float
    lsd: float
    is_significant: bool
    ci_lower: float
    ci_upper: float
    percent_change: float
    verdict_ar: str
    recommendation_ar: str

    def to_dict(self) -> dict:
        return {
            "n_blocks": self.n_blocks,
            "treatment_mean": round(self.treatment_mean, 3),
            "control_mean": round(self.control_mean, 3),
            "mean_difference": round(self.mean_difference, 3),
            "std_diff": round(self.std_diff, 4),
            "se_diff": round(self.se_diff, 4),
            "t_statistic": round(self.t_statistic, 4),
            "df": self.df,
            "p_value": round(self.p_value, 5),
            "confidence_level": self.confidence_level,
            "lsd": round(self.lsd, 4),
            "is_significant": self.is_significant,
            "ci_lower": round(self.ci_lower, 3),
            "ci_upper": round(self.ci_upper, 3),
            "percent_change": round(self.percent_change, 2),
            "verdict_ar": self.verdict_ar,
            "recommendation_ar": self.recommendation_ar,
        }


MIN_BLOCKS = 4  # معيار SARE: أقلّ من ٤ = لا صحّة إحصائيّة


def analyze_paired_trial(
    blocks: list[BlockResult],
    *,
    confidence_level: float = 0.95,
    treatment_label_ar: str = "المعالجة الجديدة",
) -> TrialVerdict:
    """يُحلّل تجربة مقترنة باختبار t مزدوج + LSD.

    يرفع ValueError لو الكتل < 4 (تقسيم الحقل لنصفَين غير صالح).
    """
    n = len(blocks)
    if n < MIN_BLOCKS:
        raise ValueError(
            f"الحدّ الأدنى {MIN_BLOCKS} كتل للصحّة الإحصائيّة (وُجد {n}). "
            "تقسيم الحقل لنصفَين أو كتلتَين لا يُنتج استنتاجاً صالحاً."
        )

    treatment = np.array([b.treatment_yield for b in blocks], dtype=float)
    control = np.array([b.control_yield for b in blocks], dtype=float)
    diffs = treatment - control

    mean_diff = float(np.mean(diffs))
    std_diff = float(np.std(diffs, ddof=1))  # عيّنة (n-1)
    se_diff = std_diff / np.sqrt(n)
    df = n - 1

    # اختبار t مزدوج (مكافئ لـttest_1samp على الفروق)
    if se_diff == 0:
        # كل الفروق متطابقة — حالة حدّيّة
        t_stat = float("inf") if mean_diff != 0 else 0.0
        p_value = 0.0 if mean_diff != 0 else 1.0
    else:
        t_stat = mean_diff / se_diff
        p_value = float(2 * (1 - stats.t.cdf(abs(t_stat), df)))

    alpha = 1 - confidence_level
    t_crit = float(stats.t.ppf(1 - alpha / 2, df))
    lsd = t_crit * se_diff
    is_sig = abs(mean_diff) > lsd

    ci_lower = mean_diff - t_crit * se_diff
    ci_upper = mean_diff + t_crit * se_diff

    control_mean = float(np.mean(control))
    treatment_mean = float(np.mean(treatment))
    pct = (mean_diff / control_mean * 100) if control_mean != 0 else 0.0

    # حُكم صادق بالعربيّة
    if is_sig:
        if mean_diff > 0:
            verdict = f"الفرق مؤكّد إحصائيّاً (p = {p_value:.3f}). {treatment_label_ar} أفضل بـ{abs(pct):.1f}%."
            rec = f"الدليل يدعم اعتماد {treatment_label_ar}."
        else:
            verdict = f"الفرق مؤكّد إحصائيّاً (p = {p_value:.3f}). المقارنة (الممارسة الحاليّة) أفضل."
            rec = "الممارسة الحاليّة أفضل — لا تغيير موصى به."
    else:
        verdict = f"لا يوجد فرق مؤكّد إحصائيّاً (p = {p_value:.3f}، LSD = {lsd:.2f})."
        rec = "الفرق قد يكون تبايناً طبيعيّاً. لا دليل كافٍ لتغيير الممارسة."

    return TrialVerdict(
        n_blocks=n,
        treatment_mean=treatment_mean,
        control_mean=control_mean,
        mean_difference=mean_diff,
        std_diff=std_diff,
        se_diff=se_diff,
        t_statistic=t_stat,
        df=df,
        p_value=p_value,
        confidence_level=confidence_level,
        lsd=lsd,
        is_significant=is_sig,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        percent_change=pct,
        verdict_ar=verdict,
        recommendation_ar=rec,
    )
