"""core/learning/prediction_calibration.py — معايرة التنبّؤ من التاريخ المتراكم.

الفكرة (المستخدم): الحقول المسجّلة (توقّع ← نتيجة فعليّة) تتراكم عبر المواسم
لتصبح **ذاكرة تاريخيّة تُحسّن التنبّؤ تدريجيّاً**. سهول يملك اللبنات:
  • recommendation_log: يسجّل (توقّع, نتيجة) + يحسب MAPE ✓
  • multi_season_analytics: اتّجاهات عبر المواسم ✓
  • trueup: معامل تصحيح k لحقل واحد ✓

الفجوة المسدودة: سهول يعرف **حجم** الخطأ (MAPE) لكن لا **اتّجاهه المنهجي**
(هل نُفرط في التقدير دائماً أم نُقلّل؟)، ولا يطبّقه لتصحيح التنبّؤ القادم.
هذا المكوّن يُغلق الحلقة: تاريخ → انحياز منهجي → تصحيح تدريجي للتنبّؤ.

⚠ المبدأ (اتّساقاً مع recommendation_log + learning_activation + farmer_agency):
  • مدفوع بالبيانات: لا تصحيح قبل عيّنة كافية (افتراضي ≥3 أزواج، ≥2 مزرعة)
  • تدريجي (لا قفزات): التصحيح يُطبَّق بمعامل تخميد (لا يلغي النموذج الأساسي)
  • صدق الانحياز: يميّز الخطأ العشوائي (MAPE عالٍ، انحياز ~0) عن المنهجي
  • لكلّ محصول×منطقة (الانحياز يختلف بالسياق)
  • شفّاف: يُعلن معامل التصحيح وسببه (لا صندوق أسود)

⚠ ليس نموذجاً يتعلّم بنفسه — تصحيح إحصائي حتمي من أزواج (توقّع, نتيجة)
موثّقة. لا اختراع: قبل الكفاية، التصحيح = 1.0 (لا تغيير) ويُعلَن السبب.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BiasType(str, Enum):
    OVERPREDICTION = "overprediction"  # نُفرط: التوقّع > الفعلي منهجيّاً
    UNDERPREDICTION = "underprediction"  # نُقلّل: التوقّع < الفعلي منهجيّاً
    UNBIASED = "unbiased"  # لا انحياز منهجي (خطأ عشوائي فقط)
    INSUFFICIENT = "insufficient"  # عيّنة غير كافية للحكم


# المبدأ: وزن متدرّج (shrinkage / Empirical Bayes) — لا عتبة حادّة.
# الوزن = n/(n+K): قرينة ضعيفة عند عيّنة صغيرة، تقوى تدريجيّاً مع البيانات.
# لا قفزة عند رقم سحري؛ الثقة تنمو بنعومة من ~0 إلى ~1.
SHRINKAGE_K = 30  # نقطة نصف الثقة: عند n=30 الوزن=0.5
MIN_PAIRS_FOR_SIGNAL = 3  # دون هذا: لا إشارة إطلاقاً (عيّنة بلا معنى)
MIN_FARMS = 2  # تجنّب pseudoreplication (مزرعة واحدة منحازة)
BIAS_SIGNIFICANCE = 0.05  # انحياز >5% يُعتبر منهجيّاً (لا عشوائيّاً)
MAX_DAMPING = 0.6  # سقف التصحيح حتّى عند عيّنة كبيرة (حذر دائم)


def confidence_weight(n: int) -> float:
    """وزن الثقة المتدرّج من حجم العيّنة (shrinkage: n/(n+K)).

    عند n صغير ⇒ وزن ضعيف (قرينة خفيفة)؛ يرتفع تدريجيّاً مع البيانات.
    n=10⇒0.25، n=30⇒0.50، n=90⇒0.75، n→∞⇒1.0. لا قفزة حادّة.
    """
    if n <= 0:
        return 0.0
    return n / (n + SHRINKAGE_K)


@dataclass
class PredictionPair:
    """زوج (توقّع, نتيجة فعليّة) من recommendation_log.

    farm_id = وحدة التكرار المستقلّة (المزرعة)، لا المستأجِر: تحت RLS يكون
    tenant_id ثابتاً، فعدّ المستأجرين لا يقيس الاستقلال الإحصائي. نعدّ المزارع
    (farm_id) لتفادي pseudoreplication الحقيقي.
    """

    predicted: float
    actual: float
    crop_id: str
    farm_id: str

    @property
    def signed_error(self) -> float:
        """الخطأ الموقّع: موجب = أفرطنا، سالب = قلّلنا (للانحياز المنهجي)."""
        if self.actual <= 0:
            return 0.0
        return (self.predicted - self.actual) / self.actual


def analyze_systematic_bias(pairs: list[PredictionPair]) -> dict:
    """يحلّل الانحياز المنهجي من أزواج تاريخيّة (الاتّجاه لا الحجم فقط).

    الفرق الجوهري عن MAPE: MAPE = متوسّط |خطأ| (الحجم). هذا = متوسّط الخطأ
    الموقّع (الاتّجاه): هل نُفرط أم نُقلّل منهجيّاً؟
    """
    n = len(pairs)
    farms = len({p.farm_id for p in pairs})

    # حدّ أدنى مطلق: دون 3 أزواج أو مزرعة واحدة، لا إشارة (عيّنة بلا معنى).
    if n < MIN_PAIRS_FOR_SIGNAL or farms < MIN_FARMS:
        return {
            "bias_type": BiasType.INSUFFICIENT.value,
            "n_pairs": n,
            "n_farms": farms,
            "confidence_weight": 0.0,
            "correction_factor": 1.0,  # لا تصحيح
            "can_calibrate": False,
            "reason_ar": (
                f"عيّنة بلا معنى إحصائي ({n} زوج، {farms} مزرعة). يلزم حدّ "
                f"أدنى {MIN_PAIRS_FOR_SIGNAL} أزواج و{MIN_FARMS} مزرعة لأيّ إشارة. "
                "لا تصحيح."
            ),
        }

    signed_errors = [p.signed_error for p in pairs]
    mean_bias = sum(signed_errors) / n
    # الوزن المتدرّج: قرينة تقوى مع البيانات (لا قفزة عند عتبة).
    weight = confidence_weight(n)

    if abs(mean_bias) < BIAS_SIGNIFICANCE:
        bias_type = BiasType.UNBIASED
        correction = 1.0
        reason = (
            f"لا انحياز منهجي (متوسّط الخطأ الموقّع {mean_bias:+.1%} ضمن "
            f"±{BIAS_SIGNIFICANCE:.0%}). خطأ عشوائي — لا تصحيح اتّجاهي."
        )
    else:
        bias_type = BiasType.OVERPREDICTION if mean_bias > 0 else BiasType.UNDERPREDICTION
        # التصحيح المطبّق = الانحياز × الوزن المتدرّج × سقف الحذر.
        # عيّنة صغيرة ⇒ وزن صغير ⇒ تصحيح خفيف (قرينة بسيطة).
        # عيّنة كبيرة ⇒ وزن قرب 1 ⇒ تصحيح أقرب للكامل (لكن دون MAX_DAMPING).
        # القصّ إلى ±MAX_DAMPING يضمن correction ∈ [1-0.6, 1+0.6] = [0.4, 1.6]:
        # انحياز ضخم (predicted≫actual) لا يُنتج معاملاً ≤0 ولا تنبّؤاً سالباً.
        applied = max(-MAX_DAMPING, min(MAX_DAMPING, mean_bias * weight * MAX_DAMPING))
        correction = round(1.0 - applied, 4)
        direction = "نُفرط في التقدير" if mean_bias > 0 else "نُقلّل التقدير"
        reason = (
            f"انحياز منهجي: {direction} بمتوسّط {mean_bias:+.1%}. "
            f"وزن الثقة {weight:.2f} (من {n} زوج) ⇒ تصحيح متدرّج ×{correction}. "
            f"القرينة تقوى كلّما زادت البيانات."
        )

    return {
        "bias_type": bias_type.value,
        "mean_signed_bias": round(mean_bias, 4),
        "n_pairs": n,
        "n_farms": farms,
        "confidence_weight": round(weight, 3),
        "correction_factor": correction,
        "can_calibrate": bias_type in (BiasType.OVERPREDICTION, BiasType.UNDERPREDICTION),
        "reason_ar": reason,
        "honesty_note_ar": (
            "قرينة بوزن متدرّج (shrinkage: الوزن = n/(n+K)). تبدأ خفيفة عند "
            "عيّنة صغيرة وتقوى تدريجيّاً مع البيانات — لا قفزة عند رقم سحري. "
            "إحصاء حتمي من أزواج موثّقة، لا نموذج يتعلّم بنفسه."
        ),
    }


def apply_calibration(raw_prediction: float, calibration: dict) -> dict:
    """يطبّق معامل التصحيح على تنبّؤ خام (شفّاف: يُظهر قبل/بعد).

    لا صندوق أسود: يُرجِع التنبّؤ الأصلي والمعدّل والمعامل والسبب.
    """
    factor = calibration.get("correction_factor", 1.0)
    calibrated = round(raw_prediction * factor, 3)
    return {
        "raw_prediction": raw_prediction,
        "calibrated_prediction": calibrated,
        "correction_factor": factor,
        "adjusted": factor != 1.0,
        "delta_pct": round((factor - 1.0) * 100, 1),
        "explanation_ar": (
            f"التنبّؤ الخام {raw_prediction} → المعدّل {calibrated} "
            f"(تصحيح {(factor - 1) * 100:+.1f}% من التاريخ المتراكم)."
            if factor != 1.0
            else f"التنبّؤ {raw_prediction} بلا تصحيح (لا انحياز منهجي/عيّنة كافية)."
        ),
    }


def calibration_maturity(pairs_by_context: dict[str, list[PredictionPair]]) -> dict:
    """نضج المعايرة عبر السياقات (محصول×منطقة) — أين نتعلّم، أين ننتظر.

    يربط الذاكرة التاريخيّة المتراكمة بقدرة التحسين لكلّ سياق.
    """
    contexts = {}
    calibrated_count = 0
    for ctx, pairs in pairs_by_context.items():
        bias = analyze_systematic_bias(pairs)
        contexts[ctx] = {
            "n_pairs": bias["n_pairs"],
            "bias_type": bias["bias_type"],
            "can_calibrate": bias["can_calibrate"],
            "correction_factor": bias["correction_factor"],
        }
        if bias["can_calibrate"]:
            calibrated_count += 1
    return {
        "total_contexts": len(pairs_by_context),
        "calibrated_contexts": calibrated_count,
        "per_context": contexts,
        "strategic_note_ar": (
            "الذاكرة التاريخيّة تنضج لكلّ سياق (محصول×منطقة) على حدة. كلّما "
            "تراكمت أزواج (توقّع,نتيجة) أكثر، تحسّن التصحيح تدريجيّاً. هذا "
            "التعلّم التدريجي الحقيقي: من بيانات فعليّة، مخمّد، شفّاف، لكلّ سياق."
        ),
    }
