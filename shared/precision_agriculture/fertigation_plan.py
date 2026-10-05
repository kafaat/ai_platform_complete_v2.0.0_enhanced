"""عقد قرار الريّ والتسميد الموحّد (المرحلة ٣) — مكتبةٌ نقيّة **غير موصولة** بأيّ قرار.

``decision-evidence-envelope.schema.json`` يفرض ``decision_domains == ["irrigation"]`` و
``fertigation_candidate_id: null`` حتّى اكتمال ``FertigationState`` (C1–C5 + C6 + قرار مالك).
هذه الوحدة لا ترفع ذلك القيد: لا يستوردها مسارُ قرار، ويحرس ذلك اختبارُها. هي تُثبّت
**الحساب والقرار** كي يُبنى عليهما حين يُرفَع الحجر، لا قبل.

ما تفرضه (من مراجعة المالك لخطّة الريّ والتسميد، 2026-10-05):

* **«ريّ فقط» هو الافتراض.** ليس كلّ فتح صمّام مناسبةً لإضافة السماد؛ الحقن قرارٌ ثانٍ
  مستقلّ بشروطه. حاجةُ مغذّيات مجهولة ⇒ ريّ فقط مع السبب.
* **لا ماء لحمل السماد.** لا حاجة مائيّة ⇒ لا رية؛ المغذّيات تُؤجَّل أو تُضاف بطريقةٍ أخرى.
* **التركيز يُحسَب خلال نافذة الحقن لا على الرية كلّها.** 16 كجم N في رية 444 م³ متوسّطُها
  36 ملجم/لتر، لكنّها خلال نصف الحجم المحقون 72 ملجم/لتر. القسمةُ على الرية كلّها تُخفي
  تضاعف التركيز.
* **جرعةٌ لا تتّسع ⇒ تجزئة،** لا زيادة الماء.
* **الأكاسيد ليست عناصر.** ملصقات الأسمدة بـP₂O₅ وK₂O؛ ``P = P₂O₅ × 0.4364`` و
  ``K = K₂O × 0.8301`` (نسبُ الكتل الذرّيّة) — الخلطُ يغيّر الجرعة.
* **وصفةٌ أو عتادٌ غير محسوم ⇒ لا حقن** مع السبب: حدُّ التركيز، ومعايرة الحاقن، وربطه بتدفّق
  الماء، ومنع الرجوع إلى البئر.
* **المحور ليس تنقيطاً.** توقيتُ الحقن على المحور مرتبطٌ بحركته وتجانس توزيعه؛ لا نموذجَ له
  هنا، فيُحجَب الحقن عليه بدل نقل وصفة التنقيط.

حدودُ الصدق: الحدود الرقميّة (حدّ التركيز، نسبة الحقن) **مدخلاتٌ** من وصفةٍ مُعتمَدة لا
ثوابت هنا؛ ولا يُشتقّ أيٌّ منها من EC وحده ولا من مؤشّر أقمار.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

#: نسب الكتل: P₂O₅ ⇒ P (2×30.974/141.945)، K₂O ⇒ K (2×39.098/94.196).
P2O5_TO_P = 0.4364
K2O_TO_K = 0.8301


def p_from_p2o5(kg_p2o5: float) -> float:
    return kg_p2o5 * P2O5_TO_P


def k_from_k2o(kg_k2o: float) -> float:
    return kg_k2o * K2O_TO_K


def p2o5_from_p(kg_p: float) -> float:
    return kg_p / P2O5_TO_P


def k2o_from_k(kg_k: float) -> float:
    return kg_k / K2O_TO_K


def gross_irrigation_m3(net_mm: float, area_ha: float, application_efficiency: float) -> float:
    """الماء الإجماليّ: ``net_mm × 10 m³/ha·mm × area ÷ Ea`` (10 مم × 4 هكتار = 400 م³ صافٍ)."""
    if not 0 < application_efficiency <= 1:
        raise ValueError("كفاءة التطبيق في (0, 1]")
    if net_mm < 0 or area_ha <= 0:
        raise ValueError("ماءٌ صافٍ سالب أو مساحةٌ غير موجبة")
    return net_mm * 10.0 * area_ha / application_efficiency


def concentration_mg_l(nutrient_kg: float, water_m3: float) -> float:
    """``kg/m³ × 1000 = mg/L``. الماء هنا حجمُ **نافذة الحقن** لا الرية كلّها."""
    if water_m3 <= 0:
        raise ValueError("حجم الماء يجب أن يكون موجباً")
    return nutrient_kg * 1000.0 / water_m3


class FertigationDecisionOutcome(str, Enum):
    """حالة **القرار** قبل التنفيذ — لا ``FertigationOutcome`` العقد (مقاييس ما بعد التنفيذ C4)."""

    NO_ACTION = "no_action"
    IRRIGATION_ONLY = "irrigation_only"
    IRRIGATION_WITH_FERTIGATION = "irrigation_with_fertigation"
    DEFER_INJECTION = "defer_injection"
    SPLIT_DOSE = "split_dose"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class InjectorReadiness:
    """شروط العتاد قبل أيّ حقن — فتحُ الصمّام وحده لا يُثبت وصول الجرعة."""

    calibrated: bool = False
    flow_interlock: bool = False
    backflow_prevention: bool = False

    def missing(self) -> list[str]:
        out = []
        if not self.calibrated:
            out.append("injector_not_calibrated")
        if not self.flow_interlock:
            out.append("injector_not_interlocked_to_water_flow")
        if not self.backflow_prevention:
            out.append("backflow_prevention_unverified")
        return out


@dataclass(frozen=True)
class FertigationInputs:
    water_need_net_mm: float  # من ميزان الماء (منطقة الجذور القانونيّة) — 0 ⇒ لا رية
    area_ha: float
    application_efficiency: float
    irrigation_method: str  # "drip" | "center_pivot" | …
    nutrient_need_kg_n: float | None = None  # None = مجهول ⇒ ريّ فقط
    injection_fraction: float | None = None  # حصّة الحقن من حجم الرية، من الوصفة
    max_injection_concentration_mg_l: float | None = None  # حدّ الوصفة المُعتمَدة
    recipe_resolved: bool = False  # الذوبانيّة والتوافق وجودة الماء محسومة
    injector: InjectorReadiness = field(default_factory=InjectorReadiness)


@dataclass(frozen=True)
class FertigationDecision:
    outcome: FertigationDecisionOutcome
    reasons: list[str]
    gross_water_m3: float | None = None
    injection_water_m3: float | None = None
    dose_now_kg_n: float = 0.0
    dose_remaining_kg_n: float = 0.0
    injection_concentration_mg_l: float | None = None
    whole_irrigation_average_mg_l: float | None = None


def _finite_nonneg(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def decide(inputs: FertigationInputs) -> FertigationDecision:
    """قرارٌ واحد من الحالات الستّ — الماءُ أوّلاً، والحقنُ شرطٌ ثانٍ لا يُفترَض."""
    if not _finite_nonneg(inputs.water_need_net_mm):
        return FertigationDecision(FertigationDecisionOutcome.BLOCKED, ["water_need_unresolved"])
    need = inputs.nutrient_need_kg_n
    if need is not None and not _finite_nonneg(need):
        return FertigationDecision(FertigationDecisionOutcome.BLOCKED, ["nutrient_need_invalid"])

    if inputs.water_need_net_mm == 0:
        if need:
            # لا ماء لحمل السماد: لا رية تُختلَق، والمغذّيات تُؤجَّل أو تُضاف بطريقةٍ أخرى.
            return FertigationDecision(
                FertigationDecisionOutcome.DEFER_INJECTION,
                ["no_water_need_do_not_irrigate_to_carry_fertilizer"],
                dose_remaining_kg_n=float(need),
            )
        return FertigationDecision(
            FertigationDecisionOutcome.NO_ACTION, ["no_water_or_nutrient_need"]
        )

    gross = gross_irrigation_m3(
        inputs.water_need_net_mm, inputs.area_ha, inputs.application_efficiency
    )
    if need is None:
        return FertigationDecision(
            FertigationDecisionOutcome.IRRIGATION_ONLY,
            ["nutrient_need_unknown"],
            gross_water_m3=gross,
        )
    if need == 0:
        return FertigationDecision(
            FertigationDecisionOutcome.IRRIGATION_ONLY, ["no_nutrient_need"], gross_water_m3=gross
        )

    blockers: list[str] = []
    if inputs.irrigation_method != "drip":
        blockers.append(f"injection_model_missing_for:{inputs.irrigation_method}")
    if not inputs.recipe_resolved:
        blockers.append("recipe_unresolved")
    frac = inputs.injection_fraction
    if not (isinstance(frac, (int, float)) and 0 < frac <= 1):
        blockers.append("injection_fraction_unresolved")
    limit = inputs.max_injection_concentration_mg_l
    if not (isinstance(limit, (int, float)) and limit > 0):
        blockers.append("injection_concentration_limit_unresolved")
    blockers.extend(inputs.injector.missing())
    if blockers:
        # الريّ يمضي، والحقن محجوبٌ بأسبابه — لا يُرفَع الحقن لأنّ الرية ستقع على كلّ حال.
        return FertigationDecision(
            FertigationDecisionOutcome.IRRIGATION_ONLY,
            ["injection_blocked", *blockers],
            gross_water_m3=gross,
            dose_remaining_kg_n=float(need),
        )

    injection_m3 = gross * float(frac)
    during = concentration_mg_l(need, injection_m3)
    average = concentration_mg_l(need, gross)
    if during <= limit:
        return FertigationDecision(
            FertigationDecisionOutcome.IRRIGATION_WITH_FERTIGATION,
            ["dose_fits_injection_window"],
            gross_water_m3=gross,
            injection_water_m3=injection_m3,
            dose_now_kg_n=float(need),
            injection_concentration_mg_l=during,
            whole_irrigation_average_mg_l=average,
        )
    # لا تتّسع: تُجزَّأ عند الحدّ، ولا يُزاد الماء لحملها.
    dose_now = limit * injection_m3 / 1000.0
    return FertigationDecision(
        FertigationDecisionOutcome.SPLIT_DOSE,
        ["dose_exceeds_injection_concentration_limit"],
        gross_water_m3=gross,
        injection_water_m3=injection_m3,
        dose_now_kg_n=dose_now,
        dose_remaining_kg_n=float(need) - dose_now,
        injection_concentration_mg_l=limit,
        whole_irrigation_average_mg_l=concentration_mg_l(dose_now, gross),
    )


def delivered_kg(
    planned_kg: float, planned_injection_m3: float, injected_before_stop_m3: float
) -> float:
    """المصالحة عند توقّف الحاقن (فقد تدفّق أو ضغط): المُنفَّذ نسبةُ الحجم المحقون فعلاً.

    يُسجَّل المُنفَّذ والمتبقّي، ولا يُفترَض أنّ الجرعة وصلت لأنّ الصمّام فُتح.
    """
    if planned_injection_m3 <= 0:
        raise ValueError("حجم الحقن المخطَّط يجب أن يكون موجباً")
    fraction = min(1.0, max(0.0, injected_before_stop_m3 / planned_injection_m3))
    return planned_kg * fraction
