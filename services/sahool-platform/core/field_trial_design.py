"""
sahool_core.field_trial_design
==============================
الذراع البحثي — تصميم التجارب الحقلية (RCBD) لتوليد المعرفة بصرامة.

النطاق: سهول منصّة قرار + بحث وتطوير + تعلّم + بناء معرفة جماعية.
هذه الوحدة تكمل حلقة المعرفة: فرضية → تجربة حقلية → قياس → تحليل →
ترقية ممارسة → بطاقة محصول → معرفة جماعية → فرضية جديدة.

تستخدم التصميم العشوائي كامل الكتل (RCBD) — معيار البحث الزراعي
(Fisher، Rothamsted، قرن من التطبيق)، لا A/B الرقمي:
  • المعاملات (treatments): ما نختبره (أصناف، أسمدة، مواعيد).
  • الكتل (blocks): قطع متجانسة تعزل تفاوت التربة (مبدأ blocking).
  • التكرار (replication): 3-5 تكرارات لكل معاملة (موثوقية).
  • العشوائية (randomization): توزيع المعاملات عشوائياً داخل كل كتلة.

التمييز عن A/B الرقمي: لا hash/طبقات/تدفّق ضخم. عيّنة صغيرة (قطع
حقل)، تحليل يناسبها (لا p-value أعمى)، أهمية عملية زراعية (MDE).

يتّكئ على: practice_promotion (تجربة ناجحة ترفع FSI)، guardrails
(السلامة تَغلِب)، measurement (توازن الكتل = التحلّل المكاني).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# الحدود العملية للتجارب الحقلية (Nebraska Extension on-farm trials)
MIN_REPLICATIONS = 3
MAX_TREATMENTS = 5      # تجارب المزرعة: لا أكثر من 5 معاملات عملياً
RECOMMENDED_REPLICATIONS = 4


@dataclass
class TrialDesign:
    treatments: list[str]
    n_blocks: int
    n_replications: int
    total_plots: int
    valid: bool
    warnings_ar: list[str] = field(default_factory=list)
    layout_note_ar: str = ""


@dataclass
class TrialAnalysis:
    treatment_means: dict
    best_treatment: str | None
    effect_size: float | None          # الفرق عن الشاهد
    meets_mde: bool                    # هل يتجاوز الحد الأدنى للمغزى؟
    practically_significant: bool
    confidence: str                    # فئوي (عيّنة صغيرة)
    promotion_signal: bool             # هل يستحقّ ترقية الممارسة؟
    note_ar: str = ""
    warnings_ar: list[str] = field(default_factory=list)


def design_rcbd(
    *,
    treatments: list[str],
    n_blocks: int,
    include_control: bool = True,
) -> TrialDesign:
    """يصمّم تجربة RCBD. الكتل تعزل تفاوت التربة؛ التكرار = عدد الكتل.

    قاعدة: لا أكثر من 5 معاملات، 3+ تكرارات (كتل). الشاهد (control)
    إلزامي — لا حكم على معاملة دون مرجع (قانون المقارنة المضادة)."""
    warnings: list[str] = []
    trts = list(treatments)
    if include_control and "control" not in [t.lower() for t in trts]:
        trts = ["شاهد"] + trts

    valid = True
    if len(trts) < 2:
        valid = False
        warnings.append("معاملتان على الأقلّ مطلوبتان (معاملة + شاهد)")
    if len(trts) > MAX_TREATMENTS + 1:
        warnings.append(
            f"عدد المعاملات ({len(trts)}) يتجاوز الموصى ({MAX_TREATMENTS}) — "
            "تجارب المزرعة تفقد الدقّة بكثرة المعاملات")
    if n_blocks < MIN_REPLICATIONS:
        valid = False
        warnings.append(
            f"الكتل ({n_blocks}) أقلّ من الحدّ الأدنى ({MIN_REPLICATIONS}) — "
            "التكرار غير كافٍ لتمييز الأثر من الضوضاء")
    elif n_blocks < RECOMMENDED_REPLICATIONS:
        warnings.append(f"يُفضّل {RECOMMENDED_REPLICATIONS} كتل لموثوقية أعلى")

    total = len(trts) * n_blocks
    return TrialDesign(
        treatments=trts, n_blocks=n_blocks, n_replications=n_blocks,
        total_plots=total, valid=valid, warnings_ar=warnings,
        layout_note_ar=(f"RCBD: {len(trts)} معاملة × {n_blocks} كتلة = {total} قطعة. "
                        "وزّع المعاملات عشوائياً داخل كل كتلة؛ الكتل تعزل تفاوت التربة."))


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return sum((v - m) ** 2 for v in values) / (len(values) - 1)


def analyze_trial(
    *,
    treatment_results: dict,      # {treatment: [قيم التكرارات]}
    control_key: str = "شاهد",
    mde_pct: float = 10.0,        # الحد الأدنى للمغزى العملي (% فرق)
) -> TrialAnalysis:
    """يحلّل نتائج التجربة بمنطق صغير-العيّنة (لا p-value أعمى).

    المبادئ: (١) الأهمية العملية (MDE) لا الإحصائية وحدها — فرق <MDE
    عديم المغزى زراعياً مهما كان 'دالّاً'. (٢) الثقة فئوية لا نسبة
    (عيّنة صغيرة). (٣) لا حكم دون شاهد. (٤) التباين العالي يمنع الترقية."""
    warnings: list[str] = []
    means = {t: round(sum(v) / len(v), 3) for t, v in treatment_results.items() if v}

    if control_key not in means:
        return TrialAnalysis(
            treatment_means=means, best_treatment=None, effect_size=None,
            meets_mde=False, practically_significant=False, confidence="none",
            promotion_signal=False,
            note_ar="لا شاهد (control) — لا حكم ممكن (قانون المقارنة المضادة)")

    control_mean = means[control_key]
    # أفضل معاملة (عدا الشاهد)
    others = {t: m for t, m in means.items() if t != control_key}
    if not others:
        return TrialAnalysis(
            treatment_means=means, best_treatment=None, effect_size=None,
            meets_mde=False, practically_significant=False, confidence="none",
            promotion_signal=False, note_ar="لا معاملات لمقارنتها بالشاهد")

    best = max(others, key=others.get)
    best_mean = others[best]
    effect = best_mean - control_mean
    effect_pct = (effect / control_mean * 100) if control_mean else 0.0
    meets_mde = abs(effect_pct) >= mde_pct

    # فحص التباين: تكرارات قليلة + تباين عالٍ → ثقة منخفضة
    n_reps = len(treatment_results.get(best, []))
    best_var = _variance(treatment_results.get(best, []))
    control_var = _variance(treatment_results.get(control_key, []))
    high_variance = best_var > best_mean if best_mean > 0 else True

    # الثقة الفئوية (عيّنة صغيرة، لا CLT)
    if n_reps < MIN_REPLICATIONS:
        confidence = "low"
        warnings.append("تكرارات قليلة — ثقة منخفضة")
    elif high_variance:
        confidence = "low"
        warnings.append("تباين عالٍ بين التكرارات — النتيجة غير مستقرّة")
    elif meets_mde and n_reps >= RECOMMENDED_REPLICATIONS:
        confidence = "medium"   # سقف التجربة الحقلية الواحدة (لا high دون تكرار مواسم)
    else:
        confidence = "low"

    # الأهمية العملية: يتجاوز MDE + ثقة معقولة
    practical = meets_mde and confidence == "medium"
    # إشارة الترقية: عملي + ليس تبايناً عالياً (يربط practice_promotion)
    promotion = practical and not high_variance

    if not meets_mde:
        note = (f"الفرق ({effect_pct:+.1f}%) دون الحد الأدنى للمغزى ({mde_pct}%) — "
                "عديم القيمة العملية مهما كان 'دالّاً' إحصائياً")
    elif promotion:
        note = (f"معاملة «{best}» تتفوّق على الشاهد بـ{effect_pct:+.1f}% "
                "(ذو مغزى عملي) — إشارة ترقية للممارسة، تحتاج تكرار مواسم للتثبيت")
    else:
        note = (f"معاملة «{best}» تتفوّق بـ{effect_pct:+.1f}% لكن الثقة محدودة — "
                "أعد التجربة موسماً آخر قبل الترقية")
    warnings.append("سقف التجربة الواحدة MEDIUM — التثبيت يحتاج تكرار مواسم (practice_promotion)")

    return TrialAnalysis(
        treatment_means=means, best_treatment=best, effect_size=round(effect, 3),
        meets_mde=meets_mde, practically_significant=practical,
        confidence=confidence, promotion_signal=promotion,
        note_ar=note, warnings_ar=warnings)
