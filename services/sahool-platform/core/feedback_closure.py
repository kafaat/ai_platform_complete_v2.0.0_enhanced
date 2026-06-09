"""
sahool_core.feedback_closure
==============================
تجهيز حلقة التغذية الراجعة — لا تطبيق learning loop، بل بنية تستقبله.

السياق: المراجعة الاستراتيجية أكّدت قرارنا بعدم بناء learning loop
الآن (بيانات outcomes غير كافية)، لكنّها اقترحت إضافة ثلاث جوهريات
كتجهيز:
  1. Success function definition (ما يُعدّ "نجاح" فعلاً؟)
  2. Lag window handling (التوصيات تظهر outcomes بعد أشهر)
  3. Bias correction (التوصيات المُنفَّذة فقط هي ما يُقاس — selection bias)

هذه الوحدة تُعرّف، لا تُطبّق. السبب: "data readiness ≠ model readiness".
محاولة tuning قبل ground truth = noise amplification.

التمييز:
  • calibration_loop: يحسب zone_factor واحد (موجود)
  • multi_season_analytics: يحلّل اتجاهات (موجود)
  • feedback_closure: يُعرّف ما يجب قياسه + كيف نتعامل مع التأخّر + bias

ما لم يُبنَ هنا (مُؤجَّل صراحةً):
  • Weight adjustment hook الفعلي
  • Gradient computation
  • Online learning
  → كلّها تنتظر outcomes كافية (50+ توصية محصودة لكل tenant)

المبادئ المحفوظة:
  • Setup before prompting: التعريفات أولاً، التشغيل لاحقاً
  • الشفّافية: كل success function قابلة للمراجعة البشرية
  • Bias awareness صريحة: لا "ML يصلح المشكلة" — نُعلن الانحيازات
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SuccessMetric(str, Enum):
    """ما الذي يُعدّ نجاحاً للتوصية؟ تعريفات صريحة قابلة للمراجعة."""

    YIELD_WITHIN_RANGE = "yield_within_range"  # الإنتاج ضمن المجال المتوقَّع
    WATER_USE_EFFICIENT = "water_use_efficient"  # WUE > baseline
    SALINITY_STABLE = "salinity_stable"  # EC لم يتزايد
    NO_SAFETY_VIOLATION = "no_safety_violation"  # PHI، حدود، إلخ
    FARMER_ACCEPTED = "farmer_accepted"  # mark_completed لا skipped
    COST_BENEFICIAL = "cost_beneficial"  # عائد ≥ تكلفة


@dataclass
class SuccessDefinition:
    """تعريف نجاح قابل للمراجعة.

    مبدأ: كل metric لها threshold صريح + reasoning زراعي.
    لا "AI يقرّر النجاح" — المهندس الزراعي يُعرّف، النظام يقيس."""

    metric: SuccessMetric
    threshold: float | None  # القيمة العتبة (إن وُجدت)
    threshold_unit: str | None
    weight: float  # 0.0-1.0 (للـcomposite score لاحقاً)
    reason_ar: str  # لماذا هذا المقياس
    requires_lab: bool = False  # هل يحتاج تحليلاً مخبرياً؟


# ─── التعريفات الافتراضية ────────────────────────────────────────

_DEFAULT_SUCCESS_DEFINITIONS = {
    SuccessMetric.YIELD_WITHIN_RANGE: SuccessDefinition(
        metric=SuccessMetric.YIELD_WITHIN_RANGE,
        threshold=0.85,  # 85% من الإنتاج المتوقَّع
        threshold_unit="ratio",
        weight=0.35,
        reason_ar="الإنتاج هو المقياس الجوهري، لكن ضمن مجال (لا رقم وحيد)",
    ),
    SuccessMetric.WATER_USE_EFFICIENT: SuccessDefinition(
        metric=SuccessMetric.WATER_USE_EFFICIENT,
        threshold=1.0,  # نسبة إلى baseline (1.0 = نفس baseline)
        threshold_unit="ratio_to_baseline",
        weight=0.20,
        reason_ar="WUE يكشف كفاءة التوصية الفعلية في السياق المائي",
    ),
    SuccessMetric.SALINITY_STABLE: SuccessDefinition(
        metric=SuccessMetric.SALINITY_STABLE,
        threshold=10.0,  # < 10% زيادة سنوية = مستقرّ
        threshold_unit="pct_per_year",
        weight=0.20,
        reason_ar="استدامة طويلة المدى — لا توصية ناجحة موسماً، فاشلة عقداً",
        requires_lab=True,
    ),
    SuccessMetric.NO_SAFETY_VIOLATION: SuccessDefinition(
        metric=SuccessMetric.NO_SAFETY_VIOLATION,
        threshold=0.0,  # zero tolerance
        threshold_unit="violations",
        weight=0.15,
        reason_ar="السلامة لا تُتخطّى — أيّ خرق PHI/حدّ = فشل تلقائي",
    ),
    SuccessMetric.FARMER_ACCEPTED: SuccessDefinition(
        metric=SuccessMetric.FARMER_ACCEPTED,
        threshold=None,  # binary: مقبولة أم لا
        threshold_unit=None,
        weight=0.10,
        reason_ar="القبول البشري إشارة وكالة المزارع — توصية مرفوضة = ضعف ثقة",
    ),
}


def get_success_definitions() -> dict:
    """يُرجع التعريفات الحالية (قابلة للقراءة، نسخة آمنة)."""
    return dict(_DEFAULT_SUCCESS_DEFINITIONS)


def composite_success_weight_sum() -> float:
    """مجموع الأوزان — يجب أن يكون قريباً من 1.0 للمراجعة."""
    return sum(d.weight for d in _DEFAULT_SUCCESS_DEFINITIONS.values())


# ─── Lag Window Handling ─────────────────────────────────────────


@dataclass
class LagWindow:
    """نافذة زمنية بين التوصية وقياس النجاح.

    التوصية بـري الذرة في مارس → الحصاد في يوليو = 4 أشهر تأخّر.
    Learning loop يجب أن:
      • لا يُحدّث الأوزان من توصيات ضمن النافذة (premature)
      • يُحدّث فقط من توصيات بـoutcomes مكتملة + متجاوزة عتبة الثقة"""

    crop_id: str
    min_lag_days: int  # أقلّ زمن لاكتمال outcome
    typical_lag_days: int  # المعتاد
    max_relevant_days: int  # بعدها outcomes "stale"
    reason_ar: str


# نوافذ افتراضية لمحاصيل سهول الأساسية (تُحدَّث من crop_cards لاحقاً)
_DEFAULT_LAG_WINDOWS = {
    "wheat": LagWindow(
        crop_id="wheat",
        min_lag_days=90,
        typical_lag_days=150,
        max_relevant_days=400,
        reason_ar="القمح: 4-5 أشهر من الزراعة للحصاد، outcomes قبل 90 يوم غير مكتملة",
    ),
    "sorghum": LagWindow(
        crop_id="sorghum",
        min_lag_days=100,
        typical_lag_days=180,
        max_relevant_days=450,
        reason_ar="الذرة الرفيعة: 4-6 أشهر، تتأثّر بالـheat stress أواخر الموسم",
    ),
    "barley": LagWindow(
        crop_id="barley",
        min_lag_days=80,
        typical_lag_days=130,
        max_relevant_days=380,
        reason_ar="الشعير: أسرع من القمح بأسبوعَين تقريباً",
    ),
    "millet": LagWindow(
        crop_id="millet",
        min_lag_days=70,
        typical_lag_days=120,
        max_relevant_days=350,
        reason_ar="الدخن: من المحاصيل قصيرة الموسم في السياق اليمني",
    ),
}


def is_outcome_ready_for_learning(
    issued_date: str,
    crop_id: str,
    current_date: str | None = None,
) -> tuple[bool, str]:
    """يفحص إن كانت التوصية ناضجة كفاية لتغذية learning loop.

    صفر اختراع: محصول غير معروف → لا نُغذّي (نُعلن السبب صراحة)."""
    if crop_id not in _DEFAULT_LAG_WINDOWS:
        return False, f"محصول '{crop_id}' لا lag window معرّفة — لا تغذية"

    window = _DEFAULT_LAG_WINDOWS[crop_id]
    now = datetime.fromisoformat(current_date) if current_date else datetime.now()

    try:
        issued = datetime.fromisoformat(issued_date.replace("Z", ""))
    except ValueError:
        # YYYY-MM-DD format
        issued = datetime.strptime(issued_date[:10], "%Y-%m-%d")

    days_elapsed = (now - issued).days

    if days_elapsed < window.min_lag_days:
        return False, (
            f"التوصية عمرها {days_elapsed} يوم — outcome غير مكتمل "
            f"(الحدّ الأدنى لـ{crop_id}: {window.min_lag_days})"
        )

    if days_elapsed > window.max_relevant_days:
        return False, (
            f"التوصية عمرها {days_elapsed} يوم — outcomes stale "
            f"(الحدّ الأقصى: {window.max_relevant_days})"
        )

    return True, (
        f"ناضجة للتغذية ({days_elapsed} يوم، "
        f"النطاق المعتاد {window.min_lag_days}-"
        f"{window.max_relevant_days})"
    )


# ─── Bias Correction Awareness ───────────────────────────────────


@dataclass
class SelectionBias:
    """انحياز الاختيار في outcomes الزراعية.

    المشكلة العميقة: نقيس outcomes فقط للتوصيات المُنفَّذة. الـskipped
    تختفي إحصائياً. هذا يُولّد bias:
      • قد تكون التوصيات الجيدة (التي يقبلها المزارع) سهلة (low-risk)
      • التوصيات الصعبة (high-impact) قد تُرفض أكثر → outcomes منخفضة
      • النتيجة: النموذج يتعلّم 'كيف أُعطي توصيات سهلة'، لا 'فعّالة'

    لا حلّ سحري — لكن وعي + counters + correction strategy:
      • نسجّل skipped explicitly مع reason_ar
      • نقيس acceptance_rate لكل crop/farm/agronomist
      • نُعلن uncertainty أكبر عند acceptance منخفض"""

    bias_type: str
    description_ar: str
    detection_method: str
    correction_strategy_ar: str


_KNOWN_BIASES = {
    "selection_bias_skipped": SelectionBias(
        bias_type="selection_bias_skipped",
        description_ar=("نقيس فقط التوصيات المُنفَّذة. المُتخطّاة تختفي من learning loop."),
        detection_method="acceptance_rate < 0.7 = signal of bias",
        correction_strategy_ar=(
            "تسجيل skipped مع reason_ar + رفع uncertainty "
            "في النموذج عند تكرار skip لنفس نوع التوصية"
        ),
    ),
    "confirmation_bias_outcomes": SelectionBias(
        bias_type="confirmation_bias_outcomes",
        description_ar=(
            "المزارعون يبلغون outcomes إيجابية أكثر من السلبية. النموذج يرى صورة وردية مزوّرة."
        ),
        detection_method="reported_yield > satellite_estimate consistently",
        correction_strategy_ar=("ground truth من حسّاسات/قمر صناعي يُرجَّح فوق البلاغ الذاتي"),
    ),
    "survivorship_bias_seasons": SelectionBias(
        bias_type="survivorship_bias_seasons",
        description_ar=(
            "مزارع فشل موسماً يتركه. نتعلّم فقط من المستمرّين. التوصيات السيّئة 'تختفي' بطرد المزارعين."
        ),
        detection_method="tenant churn rate vs avg_yield trend",
        correction_strategy_ar=("تتبّع churn explicitly + إدراج 'lost tenants' في mortality table"),
    ),
}


def known_biases() -> dict:
    """يُرجع كل الانحيازات المعروفة. الشفّافية أهمّ من الحلّ."""
    return dict(_KNOWN_BIASES)


def assess_acceptance_bias(
    total_recommendations: int,
    accepted: int,
    skipped: int,
    *,
    threshold: float = 0.7,
) -> dict:
    """يكشف selection bias في acceptance_rate.

    صفر اختراع: نقيس ونُعلن. لا نُصلح آلياً."""
    if total_recommendations == 0:
        return {"bias_risk": "unknown", "summary_ar": "لا بيانات كافية لتقييم الانحياز"}

    acceptance = accepted / total_recommendations
    skip_rate = skipped / total_recommendations

    if acceptance < threshold:
        return {
            "bias_risk": "high",
            "acceptance_rate": round(acceptance, 2),
            "skip_rate": round(skip_rate, 2),
            "summary_ar": (
                f"⚠️ معدّل القبول {acceptance:.0%} < {threshold:.0%}. "
                f"احتمال selection bias قوي. "
                f"learning loop يجب أن يأخذ skipped في الحسبان."
            ),
            "recommendation_ar": (
                "ارفع uncertainty للتوصيات من نفس النوع. راجع reasons_ar للـskipped لاكتشاف نمط."
            ),
        }
    return {
        "bias_risk": "low",
        "acceptance_rate": round(acceptance, 2),
        "skip_rate": round(skip_rate, 2),
        "summary_ar": (
            f"✅ معدّل القبول {acceptance:.0%} — selection bias منخفض ضمن النطاق المقبول."
        ),
    }


# ─── Readiness Check ─────────────────────────────────────────────


def learning_loop_readiness(
    *,
    completed_outcomes_count: int,
    acceptance_rate: float,
    lag_window_compliance: float,
    bias_assessment: str = "low",
) -> dict:
    """يفحص إن كان النظام جاهزاً لتفعيل learning loop.

    Setup before prompting: لا نُفعّل قبل توفّر:
      • 50+ outcome مكتمل لكل crop رئيسي
      • acceptance_rate >= 0.7 (selection bias منخفض)
      • >= 80% من outcomes ضمن lag window
      • bias_assessment = low"""
    blockers = []

    if completed_outcomes_count < 50:
        blockers.append(f"outcomes مكتملة {completed_outcomes_count} < 50 (الحدّ الأدنى)")

    if acceptance_rate < 0.7:
        blockers.append(f"acceptance_rate {acceptance_rate:.2f} < 0.70 (selection bias)")

    if lag_window_compliance < 0.8:
        blockers.append(f"lag compliance {lag_window_compliance:.2f} < 0.80")

    if bias_assessment != "low":
        blockers.append(f"bias assessment = {bias_assessment}, يجب 'low'")

    ready = not blockers
    return {
        "ready_for_learning": ready,
        "blockers": blockers,
        "summary_ar": (
            "✅ النظام جاهز لـlearning loop"
            if ready
            else f"⚠️ غير جاهز — {len(blockers)} حواجز: " + "؛ ".join(blockers)
        ),
    }
