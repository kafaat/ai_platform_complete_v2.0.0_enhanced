"""core/learning_activation.py — بوّابة تفعيل التعلّم المدفوعة بتدفّق البيانات.

الفكرة (طلب المستخدم): الخدمة التعلّميّة تبقى **خاملة** حتّى يتدفّق ما يكفي
من البيانات الناضجة، فتُفعَّل **تلقائيّاً** عند بلوغ العتبة. هذا يحلّ التوتّر:
لا نتعلّم من فراغ (feedback_closure مؤجّل)، لكن نُفعّل فور جاهزيّة البيانات.

ما يربطه هذا المكوّن (كان معزولاً):
  • feedback_closure.is_outcome_ready_for_learning — نضج التوصية الواحدة (زمنيّاً)
  • feedback_closure.learning_loop_readiness — معايير الجاهزيّة الكلّيّة (50+، إلخ)
  • capabilities — نمط "حاضرة خاملة حتى التزويد"
الجسر المفقود: حساب المعايير من **تدفّق البيانات الفعلي** ثمّ التفعيل التلقائي.

⚠ المبدأ:
  • التفعيل **مدفوع بالبيانات** لا بمتغيّر بيئة — العتبة شرط موضوعي
  • قبل العتبة: الخدمة خاملة **بصدق** (تُعلن "تنتظر البيانات"، لا تتظاهر بالتعلّم)
  • حتمي بالكامل: عدّ + عتبات صريحة، لا نموذج، لا اختراع
  • التفعيل **لكلّ مستأجر** (سيادة البيانات): تدفّق مستأجر A لا يفعّل خدمة B

⚠ هذا ليس "تعلّماً" بنفسه — هو **البوّابة** التي تقرّر متى يبدأ التعلّم بأمان.
حين تُفتَح، يبدأ المسار الفعلي (feedback_closure) عمله على بيانات حقيقيّة.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActivationState(str, Enum):
    """حالة بوّابة التعلّم.

    نطاق evaluate_activation: يُبلّغ حتى READY فقط (قرار البوّابة: هل يمكن البدء؟).
    ACTIVE حالة دورة حياة لاحقة يضبطها **مُتحكّم التفعيل** بعد فتح البوّابة وبدء
    التعلّم الفعلي — ليست من مخرجات evaluate_activation (لذا لا رسالة لها هنا).
    """

    DORMANT = "dormant"  # خاملة — لا بيانات كافية بعد
    ACCUMULATING = "accumulating"  # تتراكم — بيانات تتدفّق لكن دون العتبة
    READY = "ready"  # جاهزة — العتبة بُلغت، يمكن التفعيل (أقصى ما تُرجِعه البوّابة)
    ACTIVE = "active"  # مُفعَّلة — تُضبط خارج البوّابة بعد بدء التعلّم (انظر docstring)


# عتبات التفعيل (من feedback_closure.learning_loop_readiness — مصدر واحد للحقيقة)
MIN_COMPLETED_OUTCOMES = 50  # حدّ أدنى لكلّ محصول رئيسي
MIN_ACCEPTANCE_RATE = 0.70  # selection bias منخفض
MIN_LAG_COMPLIANCE = 0.80  # نضج زمني للنتائج
ACCUMULATING_FLOOR = 10  # دون هذا = خاملة؛ فوقه = تتراكم (إشارة تقدّم)


@dataclass
class DataFlowSnapshot:
    """لقطة تدفّق البيانات الفعلي (تُحسب من قاعدة البيانات لكلّ مستأجر)."""

    tenant_id: str
    completed_outcomes: int  # نتائج مكتملة (ناضجة زمنيّاً)
    total_recommendations: int  # إجماليّ التوصيات الصادرة
    accepted_recommendations: int  # المقبولة من المزارع
    outcomes_within_lag: int  # نتائج ضمن نافذة النضج الصحيحة

    @property
    def acceptance_rate(self) -> float:
        if self.total_recommendations <= 0:
            return 0.0
        return self.accepted_recommendations / self.total_recommendations

    @property
    def lag_compliance(self) -> float:
        if self.completed_outcomes <= 0:
            return 0.0
        return self.outcomes_within_lag / self.completed_outcomes


def evaluate_activation(snapshot: DataFlowSnapshot) -> dict:
    """يقرّر حالة البوّابة من لقطة التدفّق — التفعيل التلقائي عند العتبة.

    حتمي وشفّاف: يُرجِع الحالة + ما ينقص + نسبة التقدّم. لا يُفعّل خدمةً
    وهميّة — يُعلن بصدق أين نحن من العتبة.
    """
    n = snapshot.completed_outcomes
    blockers = []

    # حساب المعايير من التدفّق الفعلي
    if n < MIN_COMPLETED_OUTCOMES:
        blockers.append(
            f"نتائج مكتملة {n} < {MIN_COMPLETED_OUTCOMES} (ينقص {MIN_COMPLETED_OUTCOMES - n})"
        )
    if snapshot.acceptance_rate < MIN_ACCEPTANCE_RATE:
        blockers.append(
            f"قبول {snapshot.acceptance_rate:.0%} < {MIN_ACCEPTANCE_RATE:.0%} (انحياز اختيار محتمل)"
        )
    if n > 0 and snapshot.lag_compliance < MIN_LAG_COMPLIANCE:
        blockers.append(f"نضج زمني {snapshot.lag_compliance:.0%} < {MIN_LAG_COMPLIANCE:.0%}")

    # تحديد الحالة
    if not blockers:
        state = ActivationState.READY
    elif n >= ACCUMULATING_FLOOR:
        state = ActivationState.ACCUMULATING
    else:
        state = ActivationState.DORMANT

    progress = min(1.0, n / MIN_COMPLETED_OUTCOMES) if MIN_COMPLETED_OUTCOMES else 0.0

    state_msg = {
        ActivationState.DORMANT: "خاملة — تنتظر تدفّق بيانات كافٍ (لا تعلّم من فراغ)",
        ActivationState.ACCUMULATING: "تتراكم — البيانات تتدفّق، نقترب من العتبة",
        ActivationState.READY: "جاهزة — العتبة بُلغت، التعلّم يمكن أن يبدأ بأمان",
    }[state]

    return {
        "tenant_id": snapshot.tenant_id,
        "state": state.value,
        "state_ar": state_msg,
        "progress_pct": round(progress * 100, 1),
        "completed_outcomes": n,
        "threshold": MIN_COMPLETED_OUTCOMES,
        "acceptance_rate": round(snapshot.acceptance_rate, 2),
        "lag_compliance": round(snapshot.lag_compliance, 2),
        "blockers": blockers,
        "can_activate": state == ActivationState.READY,
        "honesty_note_ar": (
            "البوّابة مدفوعة بالبيانات: لا تُفعّل التعلّم قبل توفّر نتائج حقيقيّة "
            "كافية وناضجة. قبل ذلك تبقى خاملة بصدق — لا تتظاهر بتعلّم لم يبدأ."
        ),
    }


def activation_summary(snapshots: list[DataFlowSnapshot]) -> dict:
    """ملخّص حالة التفعيل عبر المستأجرين (لوحة حوكمة).

    كلّ مستأجر مستقلّ (سيادة البيانات): قد يكون A جاهزاً وB خاملاً.
    """
    evals = [evaluate_activation(s) for s in snapshots]
    ready = [e for e in evals if e["can_activate"]]
    return {
        "total_tenants": len(snapshots),
        "ready_to_activate": len(ready),
        "per_tenant": evals,
        "note_ar": (
            "التفعيل لكلّ مستأجر على حدة — تدفّق مستأجر لا يفعّل خدمة آخر "
            "(سيادة البيانات). الخدمة تُفعَّل حيث نضجت البيانات فقط."
        ),
    }
