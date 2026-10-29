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
  • التكرار (replication): سياسة المنتج تقبل 3 كحد أدنى وتوصي بـ4 كتل.
  • العشوائية (randomization): توزيع المعاملات عشوائياً داخل كل كتلة.

التمييز عن A/B الرقمي: لا hash/طبقات/تدفّق ضخم. عيّنة صغيرة (قطع
حقل)، تحليل يناسبها (لا p-value أعمى)، أهمية عملية زراعية (MDE).

يتّكئ على: practice_promotion (تجربة ناجحة ترفع FSI)، guardrails
(السلامة تَغلِب)، measurement (توازن الكتل = التحلّل المكاني).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Integral
from statistics import fmean, stdev

# سياسة المنتج: 3 كتل حد أدنى للتصميم، و4 موصى بها للفحص الوصفي.
# هذه الحدود ليست ضماناً عاماً للقوة أو الصلاحية الإحصائية.
MIN_REPLICATIONS = 3
MAX_TREATMENTS = 5  # تجارب المزرعة: لا أكثر من 5 معاملات عملياً
RECOMMENDED_REPLICATIONS = 4
_CONTROL_ALIASES = {"control", "شاهد"}


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
    effect_size: float | None  # الفرق عن الشاهد
    meets_mde: bool  # هل يتجاوز الحد الأدنى للمغزى؟
    practically_significant: bool
    confidence: str  # فئوي (عيّنة صغيرة)
    promotion_signal: bool  # هل يستحقّ ترقية الممارسة؟
    note_ar: str = ""
    warnings_ar: list[str] = field(default_factory=list)


def _treatment_identity(label: str) -> str:
    normalized = label.strip().casefold()
    return "control" if normalized in _CONTROL_ALIASES else normalized


def _treatment_labels(labels: list[str]) -> list[str]:
    """Keep display names, but reject ambiguous or empty treatment identities."""
    normalized = []
    seen = set()
    for label in labels:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("اسم المعاملة يجب أن يكون نصاً غير فارغ")
        identity = _treatment_identity(label)
        if identity in seen:
            raise ValueError(f"اسم معاملة مكرر: {label.strip()}")
        seen.add(identity)
        normalized.append(label.strip())
    return normalized


def _finite_number(value: float, *, name: str) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name}: يلزم عدد محدود") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name}: يلزم عدد محدود")
    return number


def design_rcbd(
    *,
    treatments: list[str],
    n_blocks: int,
    include_control: bool = True,
) -> TrialDesign:
    """يصمّم تجربة RCBD. الكتل تعزل تفاوت التربة؛ التكرار = عدد الكتل.

    سياسة المنتج: 3 كتل على الأقل و4 موصى بها، وليست ضماناً للقوة الإحصائية.
    يضاف الشاهد افتراضياً إن لم يوجد بالعربية أو الإنجليزية؛ تعطيل إضافته
    لا يتيح تحليل أثر المعاملة دون مرجع."""
    if isinstance(n_blocks, bool) or not isinstance(n_blocks, Integral) or n_blocks < 1:
        raise ValueError("n_blocks must be a positive integer")
    n_blocks = int(n_blocks)
    warnings: list[str] = []
    trts = _treatment_labels(treatments)
    if include_control and not any(_treatment_identity(t) == "control" for t in trts):
        trts = ["شاهد"] + trts

    valid = True
    if len(trts) < 2:
        valid = False
        warnings.append("معاملتان على الأقلّ مطلوبتان (معاملة + شاهد)")
    if len(trts) > MAX_TREATMENTS + 1:
        warnings.append(
            f"عدد المعاملات ({len(trts)}) يتجاوز الموصى ({MAX_TREATMENTS}) — "
            "تجارب المزرعة تفقد الدقّة بكثرة المعاملات"
        )
    if n_blocks < MIN_REPLICATIONS:
        valid = False
        warnings.append(
            f"الكتل ({n_blocks}) أقلّ من الحدّ الأدنى ({MIN_REPLICATIONS}) — "
            "لا يحقق سياسة الحد الأدنى للتصميم"
        )
    elif n_blocks < RECOMMENDED_REPLICATIONS:
        warnings.append(f"يُفضّل {RECOMMENDED_REPLICATIONS} كتل لموثوقية أعلى")

    total = len(trts) * n_blocks
    return TrialDesign(
        treatments=trts,
        n_blocks=n_blocks,
        n_replications=n_blocks,
        total_plots=total,
        valid=valid,
        warnings_ar=warnings,
        layout_note_ar=(
            f"RCBD: {len(trts)} معاملة × {n_blocks} كتلة = {total} قطعة. "
            "وزّع المعاملات عشوائياً داخل كل كتلة؛ الكتل تعزل تفاوت التربة."
        ),
    )


def analyze_trial(
    *,
    treatment_results: dict,  # {treatment: [قيم التكرارات]}
    control_key: str = "شاهد",
    mde_pct: float = 10.0,  # الحد الأدنى للمغزى العملي (% فرق)
) -> TrialAnalysis:
    """فحص وصفي لنتائج مقياس تكون قيمته الأعلى أفضل، مثل المحصول.

    كل قيمة تمثل قطعة تجريبية مستقلة؛ يجب أن تتطابق قوائم المعاملة والشاهد
    بالكتلة وبالترتيب، ولا تُعد القياسات الزمنية أو العينات الفرعية تكرارات.
    اختلاف طول القوائم يسمح بوصف المتوسطات فقط ويمنع الترقية.

    سياسة الفحص: تحسن موجب يبلغ MDE، وأربع أزواج على الأقل، ونسبة الانحراف
    المعياري لفروق الأزواج إلى مقدار متوسطها <=1. النسبة بلا وحدة وتشمل
    تباين الشاهد بعد حجب أثر الكتلة المشترك. هذه قاعدة منتج وصفية، وليست
    اختبار دلالة أو ضماناً للقوة الإحصائية؛ سقف الثقة في تجربة واحدة medium.
    """
    mde_pct = _finite_number(mde_pct, name="mde_pct")
    if mde_pct <= 0:
        raise ValueError("mde_pct يجب أن يكون موجباً")
    labels = _treatment_labels(list(treatment_results))
    control_key = _treatment_labels([control_key])[0]
    results = {
        label: [_finite_number(value, name=label) for value in values]
        for label, values in zip(labels, treatment_results.values(), strict=True)
    }
    warnings: list[str] = []
    try:
        raw_means = {t: _finite_number(fmean(v), name=t) for t, v in results.items() if v}
    except OverflowError as exc:
        raise ValueError("Trial magnitudes exceed the finite analysis range") from exc
    # Round only presentation values, never the screening decision.
    means = {t: round(mean, 3) for t, mean in raw_means.items()}
    control_label = next(
        (t for t in raw_means if _treatment_identity(t) == _treatment_identity(control_key)),
        None,
    )

    if control_label is None:
        return TrialAnalysis(
            treatment_means=means,
            best_treatment=None,
            effect_size=None,
            meets_mde=False,
            practically_significant=False,
            confidence="none",
            promotion_signal=False,
            note_ar="لا شاهد (control) — لا حكم ممكن (قانون المقارنة المضادة)",
        )

    control_mean = raw_means[control_label]
    # أفضل معاملة (عدا الشاهد)
    others = {t: m for t, m in raw_means.items() if t != control_label}
    if not others:
        return TrialAnalysis(
            treatment_means=means,
            best_treatment=None,
            effect_size=None,
            meets_mde=False,
            practically_significant=False,
            confidence="none",
            promotion_signal=False,
            note_ar="لا معاملات لمقارنتها بالشاهد",
        )

    best = max(others, key=others.get)
    best_mean = others[best]
    control_values = results[control_label]
    best_values = results[best]
    paired = len(best_values) == len(control_values)
    effect = _finite_number(best_mean - control_mean, name="effect")
    differences = (
        [
            _finite_number(t - c, name="difference")
            for t, c in zip(best_values, control_values, strict=True)
        ]
        if paired
        else []
    )
    try:
        if differences:
            effect = _finite_number(fmean(differences), name="effect")
        spread = _finite_number(stdev(differences), name="spread") if len(differences) > 1 else 0.0
    except OverflowError as exc:
        raise ValueError("Trial magnitudes exceed the finite analysis range") from exc
    effect_pct = _finite_number(
        (effect / control_mean * 100) if control_mean > 0 else 0.0, name="effect_pct"
    )
    meets_mde = effect > 0 and control_mean > 0 and effect_pct >= mde_pct

    # sd(diff) / abs(mean(diff)) > 1, expressed without division at zero.
    high_variance = len(differences) > 1 and spread > abs(effect)
    n_pairs = len(differences)
    confidence = "low"
    if not paired:
        warnings.append("تكرارات المعاملة والشاهد غير متساوية — لا مقارنة مقترنة ولا ترقية")
    elif n_pairs < MIN_REPLICATIONS:
        warnings.append("تكرارات مقترنة قليلة — ثقة منخفضة")
    elif high_variance:
        warnings.append("تباين عالٍ في فروق المعاملة والشاهد بين الكتل — النتيجة غير مستقرّة")
    elif meets_mde and n_pairs >= RECOMMENDED_REPLICATIONS:
        confidence = "medium"  # سقف التجربة الحقلية الواحدة (لا high دون تكرار مواسم)
    elif n_pairs < RECOMMENDED_REPLICATIONS:
        warnings.append(f"سياسة الفحص الوصفي تتطلب {RECOMMENDED_REPLICATIONS} أزواج لإشارة الترقية")
    if control_mean <= 0:
        warnings.append("متوسط الشاهد غير موجب — التحسن النسبي غير قابل للتقييم")

    # الأهمية العملية: يتجاوز MDE + ثقة معقولة
    practical = meets_mde and confidence == "medium"
    # إشارة الترقية: عملي + ليس تبايناً عالياً (يربط practice_promotion)
    promotion = practical and not high_variance

    if control_mean <= 0:
        note = "لا يمكن تقييم عتبة التحسن النسبي مع متوسط شاهد غير موجب — لا إشارة ترقية"
    elif effect <= 0:
        note = f"معاملة «{best}» لا تتفوّق على الشاهد (الفرق {effect_pct:+.1f}%) — لا إشارة ترقية"
    elif not meets_mde:
        note = (
            f"الزيادة ({effect_pct:+.1f}%) دون عتبة التحسن العملي المختارة ({mde_pct}%) — "
            "لا إشارة ترقية وفق سياسة الفحص"
        )
    elif promotion:
        note = (
            f"معاملة «{best}» تتفوّق على الشاهد بـ{effect_pct:+.1f}% "
            "وفق الفحص الوصفي — إشارة ترقية للمراجعة، تحتاج تكرار مواسم للتثبيت"
        )
    else:
        note = (
            f"معاملة «{best}» تتفوّق بـ{effect_pct:+.1f}% لكن الثقة محدودة — "
            "أعد التجربة موسماً آخر قبل الترقية"
        )
    warnings.append("سقف التجربة الواحدة MEDIUM — التثبيت يحتاج تكرار مواسم (practice_promotion)")
    warnings.append("هذا فحص وصفي وفق سياسة المنتج، وليس اختبار دلالة إحصائية")

    return TrialAnalysis(
        treatment_means=means,
        best_treatment=best,
        effect_size=round(effect, 3),
        meets_mde=meets_mde,
        practically_significant=practical,
        confidence=confidence,
        promotion_signal=promotion,
        note_ar=note,
        warnings_ar=warnings,
    )
