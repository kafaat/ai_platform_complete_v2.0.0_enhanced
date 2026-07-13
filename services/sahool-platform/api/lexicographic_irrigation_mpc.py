"""api/lexicographic_irrigation_mpc.py — متحكّم تنبّؤيّ هرميّ معجميّ للريّ (Lexicographic MPC, المرحلة 0)

يُعمّم المُخطِّط الجشِع `api/irrigation_mpc.plan_irrigation` من **سياسة واحدة** إلى
**اختيار معجميّ (lexicographic)** بين خطط مرشَّحة، وفق سلّم أولويّات صارم غير قابل
للمقايضة الماليّة:

  الأولوية 1 (J1): حماية المحصول من الإجهاد الحرج  — Dr ≤ RAW + ساعات/أيّام إجهاد
                    مُثقَّلة بحسّاسيّة المرحلة (Ky, FAO-33).
  الأولوية 2 (J2): تقليل استهلاك الماء (والطاقة)   — ماء مُطبَّق + رشح عميق. الطاقة
                    **غير مُنمذَجة** في هذه المرحلة (لا بيانات آبار/مضخّات/شمسيّة) —
                    تُعلَن `not_modeled` صراحةً ولا تُلفَّق.
  الأولوية 3 (J3): الحفاظ على حدّ إنتاج أدنى        — في المرحلة 0 وكيلٌ قائم على الإجهاد
                    في المراحل الحرجة (`stress_proxy_pending_ky`)؛ يُستبدَل بمعادلة Ky
                    الكنسيّة `Ya/Ym = 1−Ky·(1−ETa/ETm)` في المرحلة 1.
  الأولوية 4 (J4): تعظيم الهامش الاقتصاديّ          — وكيل تكلفة ماء ($/m³). الإيراد
                    والطاقة غير مُنمذَجَين — `not_modeled`.

الاختيار المعجميّ بهامش ε: نُثبّت أفضل J1، ثمّ نبحث ضمن الهامش عن أفضل J2، ثمّ J3، ثمّ
J4 — لا يُسمح لمستوى أدنى بتحسين نتيجته إن أضرّ بمستوى أعلى خارج هامش السماح.

نقيّ حتميّ (لا I/O، لا شبكة، لا عشوائيّة). **توصية-فقط**: `approval_required=True` دائماً
في المرحلة 0؛ القرار والموافقة والتنفيذ تبقى في مركز القرار عبر السلسلة القائمة. المقابض
والأوزان أوّليّة (`calibrated=False`) تحتاج معايرة يمنيّة. يعيد استخدام `plan_irrigation`
كمُحاكٍ أماميّ و`_STAGE_SENSITIVITY` (Ky) لِوزن المراحل الحرجة.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# حسّاسيّة المرحلة (Ky القياسيّة FAO-33) — المصدر الأوحد في supplemental_irrigation.
from core.engines.supplemental_irrigation import _STAGE_SENSITIVITY

# نغمة الإجهاد الكنسيّة (AWF) — نعيد استخدام أوّليّات canonical_water_stress نفسها.
from api.canonical_water_stress import WATER_STRESS_CRITICAL_AWF
from api.irrigation_mpc import ForecastDay, IrrigationPlan, plan_irrigation
from api.irrigation_policy import IrrigationPolicy
from api.soil_water import available_water_fraction

# مرحلة حرجة إن كانت حساسيّة Ky ≥ هذه العتبة (الإزهار/امتلاء الحبّ) — نفس عتبة النظام.
CRITICAL_STAGE_KY = 0.85

# أوزان/هوامش أوّليّة — ⚠ غير معايَرة (calibrated=False).
LAMBDA_STRESS = 25.0  # وزن يوم إجهاد في مرحلة حرجة داخل J1
EPS_J1 = 1e-6  # هامش سماح J1 (حماية المحصول شبه غير قابلة للمقايضة)
EPS_J2_MM = 2.0  # هامش سماح J2 (مم ماء) للانتقال إلى J3
EPS_J3 = 1e-6  # هامش سماح J3
WATER_WASTE_PENALTY = 1.0  # وزن الرشح العميق ضمن J2 (مم لكلّ مم)

# مجموعة السياسات المرشَّحة (فضاء القرار المُنفصِل الحتميّ) — كلّ الخمس القائمة.
_CANDIDATE_POLICIES: tuple[IrrigationPolicy, ...] = (
    IrrigationPolicy.RISK_AVERSE,
    IrrigationPolicy.YIELD_MAX,
    IrrigationPolicy.PROFIT_MAX,
    IrrigationPolicy.WATER_SAVING,
    IrrigationPolicy.SUSTAINABILITY,
)

# الحقول المُؤجَّلة صراحةً في المرحلة 0 (تُعلَن ولا تُلفَّق).
_NOT_MODELLED_PHASE0: tuple[str, ...] = (
    "predicted_energy_kwh",  # يحتاج طبقة الطاقة/المضخّة (المرحلة 2)
    "source_well_id",  # يحتاج نموذج الآبار (المرحلة 2)
    "start_at",  # يحتاج أفقاً ساعيّاً (المرحلة 3)
    "duration_minutes",  # يحتاج معدّل تطبيق/تدفّق (المرحلة 3)
    "zone_id",  # يحتاج قراراً على مستوى المناطق (لاحقاً)
    "economic_margin_delta.revenue",  # الإيراد غير مُنمذَج (وكيل تكلفة فقط)
)


class ReasonCode(str, Enum):
    """رموز أسباب معدودة — مفردات صريحة بدل النصّ الحرّ."""

    ROOT_ZONE_APPROACHING_RAW = "ROOT_ZONE_APPROACHING_RAW"
    ROOT_ZONE_BELOW_RAW = "ROOT_ZONE_BELOW_RAW"  # إجهاد فعليّ الآن
    CRITICAL_GROWTH_STAGE = "CRITICAL_GROWTH_STAGE"
    STRESS_FORECAST = "STRESS_FORECAST"  # إجهاد متوقّع في الأفق
    WATER_BUDGET_LIMITED = "WATER_BUDGET_LIMITED"
    DEEP_PERCOLATION_RISK = "DEEP_PERCOLATION_RISK"
    RAIN_EXPECTED_HOLD = "RAIN_EXPECTED_HOLD"  # مطر متوقّع يكفي ⇒ تأجيل
    NORMAL_SCHEDULE = "NORMAL_SCHEDULE"
    DATA_DEGRADED = "DATA_DEGRADED"
    MISSING_CRITICAL_INPUTS = "MISSING_CRITICAL_INPUTS"


class OperatingState(str, Enum):
    """حالات التشغيل — تحدّد أيّ منطق يقود القرار."""

    NORMAL_OPTIMIZATION = "NORMAL_OPTIMIZATION"
    CROP_PROTECTION = "CROP_PROTECTION"
    WATER_SCARCITY = "WATER_SCARCITY"
    ENERGY_CONSTRAINED = "ENERGY_CONSTRAINED"  # غير قابلة للوصول في المرحلة 0 (لا طاقة)
    DATA_DEGRADED = "DATA_DEGRADED"
    EMERGENCY_FAIL_CLOSED = "EMERGENCY_FAIL_CLOSED"


@dataclass
class LexObjectives:
    """قيم الأهداف الأربعة لخطّة مرشَّحة (كلّها «أقلّ أفضل»)."""

    j1_crop_protection: float
    j2_water: float
    j3_yield_shortfall: float
    j4_water_cost: float
    energy_modelled: bool = False  # J2 يشمل الطاقة؟ (المرحلة 0: لا)

    def to_dict(self) -> dict:
        return {
            "j1_crop_protection": round(self.j1_crop_protection, 4),
            "j2_water": round(self.j2_water, 4),
            "j3_yield_shortfall": round(self.j3_yield_shortfall, 6),
            "j4_water_cost": round(self.j4_water_cost, 4),
            "energy_modelled": self.energy_modelled,
        }


@dataclass
class LexicographicIrrigationDecision:
    """قرار الريّ المعجميّ — عقد المرحلة 0 (توصية-فقط)."""

    decision: str  # "irrigate" | "hold"
    field_id: str | None
    operating_state: OperatingState
    selected_policy: str | None
    horizon_days: int
    target_depth_mm: float  # عمق ريّ اليوم (أوّل يوم في الأفق)
    predicted_water_m3_per_ha: float  # 1 مم = 10 م³/هكتار (المساحة الفعليّة عند المتّصِل)
    root_zone_depletion_before_mm: float
    expected_root_zone_depletion_after_mm: float
    raw_mm: float
    taw_mm: float
    stress_risk_before: str  # normal | watch | critical (نغمة كنسيّة)
    stress_risk_after: str
    stress_days_in_horizon: list[int]
    yield_floor_preserved: bool
    yield_floor_basis: str  # "stress_proxy_pending_ky" (المرحلة 0)
    water_cost_proxy: float | None  # J4 وكيل — الإيراد غير مُنمذَج
    economic_margin_delta: float | None  # None في المرحلة 0 (لا إيراد)
    confidence: float
    approval_required: bool  # True دائماً في المرحلة 0
    reason_codes: list[ReasonCode]
    objectives: LexObjectives | None
    not_modelled: list[str]
    calibrated: bool
    notes_ar: list[str]

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "field_id": self.field_id,
            "operating_state": self.operating_state.value,
            "selected_policy": self.selected_policy,
            "horizon_days": self.horizon_days,
            "target_depth_mm": round(self.target_depth_mm, 2),
            "predicted_water_m3_per_ha": round(self.predicted_water_m3_per_ha, 2),
            "root_zone_depletion_before_mm": round(self.root_zone_depletion_before_mm, 2),
            "expected_root_zone_depletion_after_mm": round(
                self.expected_root_zone_depletion_after_mm, 2
            ),
            "raw_mm": round(self.raw_mm, 2),
            "taw_mm": round(self.taw_mm, 2),
            "stress_risk_before": self.stress_risk_before,
            "stress_risk_after": self.stress_risk_after,
            "stress_days_in_horizon": self.stress_days_in_horizon,
            "yield_floor_preserved": self.yield_floor_preserved,
            "yield_floor_basis": self.yield_floor_basis,
            "water_cost_proxy": (
                None if self.water_cost_proxy is None else round(self.water_cost_proxy, 4)
            ),
            "economic_margin_delta": self.economic_margin_delta,
            "confidence": round(self.confidence, 3),
            "approval_required": self.approval_required,
            "reason_codes": [c.value for c in self.reason_codes],
            "objectives": None if self.objectives is None else self.objectives.to_dict(),
            "not_modelled": self.not_modelled,
            "calibrated": self.calibrated,
            "notes_ar": self.notes_ar,
        }


def _risk_class(dr_mm: float, taw_mm: float, p: float) -> str:
    """نغمة الإجهاد الكنسيّة من AWF — نفس عتبات canonical_water_stress."""
    awf = available_water_fraction(dr_mm, taw_mm)
    if awf <= WATER_STRESS_CRITICAL_AWF:
        return "critical"
    if awf <= (1.0 - p):
        return "watch"
    return "normal"


def _stage_ky(growth_stage: str | None) -> float:
    if not growth_stage:
        return 0.55  # افتراض تحفّظيّ (متوسّط) عند غياب المرحلة
    return _STAGE_SENSITIVITY.get(str(growth_stage).strip().lower(), 0.55)


def _score_plan(
    plan: IrrigationPlan, is_critical_stage: bool, water_price_per_m3: float | None
) -> LexObjectives:
    """يسجّل خطّة على الأهداف الأربعة — كلّها «أقلّ أفضل»."""
    raw = plan.raw_mm
    j1 = 0.0
    j3_shortfall = 0.0
    for d in plan.days:
        over = max(0.0, d.dr_end_mm - raw)
        j1 += over * over  # مربّع تجاوز RAW (يعاقب الإجهاد بشدّة)
        if d.stressed and is_critical_stage:
            j1 += LAMBDA_STRESS
            # وكيل نقص الإنتاج (المرحلة 0): نسبة تجاوز RAW في المراحل الحرجة.
            j3_shortfall += over / raw if raw > 0 else 0.0

    j2 = plan.total_irrigation_mm + WATER_WASTE_PENALTY * plan.total_deep_perc_mm
    # J4 وكيل تكلفة الماء (الإيراد/الطاقة غير مُنمذَجَين).
    price = water_price_per_m3 if water_price_per_m3 and water_price_per_m3 > 0 else 0.0
    j4 = plan.total_irrigation_m3_ha * price
    return LexObjectives(
        j1_crop_protection=j1,
        j2_water=j2,
        j3_yield_shortfall=j3_shortfall,
        j4_water_cost=j4,
        energy_modelled=False,
    )


def _lexicographic_select(
    scored: list[tuple[IrrigationPlan, LexObjectives]],
) -> tuple[IrrigationPlan, LexObjectives]:
    """اختيار معجميّ بهامش ε: J1 ثمّ J2 ثمّ J3 ثمّ J4، لا مقايضة عبر المستويات."""
    # المستوى 1: أفضل J1 ضمن الهامش.
    best_j1 = min(s.j1_crop_protection for _, s in scored)
    s1 = [(p, s) for (p, s) in scored if s.j1_crop_protection <= best_j1 + EPS_J1]
    # المستوى 2: ضمن s1، أفضل J2 ضمن الهامش.
    best_j2 = min(s.j2_water for _, s in s1)
    s2 = [(p, s) for (p, s) in s1 if s.j2_water <= best_j2 + EPS_J2_MM]
    # المستوى 3: ضمن s2، أفضل J3 ضمن الهامش.
    best_j3 = min(s.j3_yield_shortfall for _, s in s2)
    s3 = [(p, s) for (p, s) in s2 if s.j3_yield_shortfall <= best_j3 + EPS_J3]
    # المستوى 4: ضمن s3، أدنى J4 (كسر التعادل حتميّ بترتيب المرشّحين).
    return min(s3, key=lambda ps: ps[1].j4_water_cost)


def _emergency_decision(
    field_id: str | None, reason: ReasonCode, note_ar: str
) -> LexicographicIrrigationDecision:
    """قرار فاشل-مُغلَق محافظ: لا أمر تنفيذ، موافقة بشريّة، ثقة دنيا."""
    return LexicographicIrrigationDecision(
        decision="hold",
        field_id=field_id,
        operating_state=OperatingState.EMERGENCY_FAIL_CLOSED,
        selected_policy=None,
        horizon_days=0,
        target_depth_mm=0.0,
        predicted_water_m3_per_ha=0.0,
        root_zone_depletion_before_mm=0.0,
        expected_root_zone_depletion_after_mm=0.0,
        raw_mm=0.0,
        taw_mm=0.0,
        stress_risk_before="unknown",
        stress_risk_after="unknown",
        stress_days_in_horizon=[],
        yield_floor_preserved=False,
        yield_floor_basis="unavailable",
        water_cost_proxy=None,
        economic_margin_delta=None,
        confidence=0.0,
        approval_required=True,
        reason_codes=[reason],
        objectives=None,
        not_modelled=list(_NOT_MODELLED_PHASE0),
        calibrated=False,
        notes_ar=[note_ar],
    )


def solve_lexicographic_irrigation(
    *,
    forecast: list[ForecastDay],
    taw_mm: float,
    raw_fraction: float,
    initial_depletion_mm: float,
    field_id: str | None = None,
    growth_stage: str | None = None,
    max_application_mm: float | None = None,
    season_budget_mm: float | None = None,
    water_price_per_m3: float | None = None,
    depletion_confidence: float | None = None,
    data_degraded: bool = False,
) -> LexicographicIrrigationDecision:
    """يحلّ قرار الريّ معجميّاً على أفق يوميّ — نقيّ حتميّ، توصية-فقط.

    فشل-مُغلَق عند غياب المدخلات الحرجة (لا أفق، TAW/RAW غير صالح): يعيد قراراً محافظاً
    بموافقة بشريّة بدل اختلاق أمر. عند التدهور الجزئيّ (`data_degraded` أو ثقة استنزاف
    منخفضة) يوسّع هامش الأمان (سياسة تجنّب-الخطر تُفضَّل ضمنيّاً عبر السلّم) ويخفض الثقة.
    """
    # فشل-مُغلَق: مدخلات حرجة مفقودة/غير صالحة.
    if not forecast:
        return _emergency_decision(
            field_id, ReasonCode.MISSING_CRITICAL_INPUTS, "لا أفق تنبّؤ — لا قرار ريّ ممكن"
        )
    if taw_mm <= 0.0 or not (0.0 < raw_fraction <= 1.0):
        return _emergency_decision(
            field_id, ReasonCode.MISSING_CRITICAL_INPUTS, "TAW/RAW غير صالح — فشل مُغلَق"
        )

    raw_mm = raw_fraction * taw_mm
    is_critical = _stage_ky(growth_stage) >= CRITICAL_STAGE_KY

    # محاكاة كلّ سياسة مرشَّحة أماماً، ثمّ تسجيلها.
    scored: list[tuple[IrrigationPlan, LexObjectives]] = []
    for pol in _CANDIDATE_POLICIES:
        plan = plan_irrigation(
            forecast,
            taw_mm=taw_mm,
            raw_fraction=raw_fraction,
            policy=pol,
            initial_depletion_mm=initial_depletion_mm,
            max_application_mm=max_application_mm,
            season_budget_mm=season_budget_mm,
            water_price_per_m3=water_price_per_m3,
        )
        scored.append((plan, _score_plan(plan, is_critical, water_price_per_m3)))

    winner, obj = _lexicographic_select(scored)

    day0 = winner.days[0]
    target_depth = day0.irrigation_mm
    dr_before = day0.dr_before_irrig_mm
    dr_after = day0.dr_end_mm
    decision = "irrigate" if target_depth > 0.0 else "hold"

    # نغمة الإجهاد الكنسيّة (AWF = 1 − Dr/TAW).
    risk_before = _risk_class(initial_depletion_mm, taw_mm, raw_fraction)
    risk_after = _risk_class(dr_after, taw_mm, raw_fraction)

    # J3 وكيل: نعتبر حدّ الإنتاج محفوظاً إن لم يوجد إجهاد حرج في الأفق للخطّة الفائزة.
    yield_floor_preserved = obj.j3_yield_shortfall <= EPS_J3

    # تحديد حالة التشغيل. حماية المحصول: مرحلة حرجة مع اقتراب/تجاوز الاستنزاف لـRAW
    # (dr_before ≥ RAW يعني عبور العتبة خلال اليوم) أو تنبيه/إجهاد متوقّع.
    approaching_critical = dr_before >= raw_mm or risk_before in ("watch", "critical")
    if winner.budget_exhausted and winner.stress_days:
        state = OperatingState.WATER_SCARCITY
    elif is_critical and (approaching_critical or winner.stress_days):
        state = OperatingState.CROP_PROTECTION
    elif data_degraded or (depletion_confidence is not None and depletion_confidence < 0.5):
        state = OperatingState.DATA_DEGRADED
    else:
        state = OperatingState.NORMAL_OPTIMIZATION

    # رموز الأسباب.
    reasons: list[ReasonCode] = []
    trigger_threshold = raw_mm  # الإطلاق العمليّ يقع قرب RAW (trigger_fraction≈1 للسياسات المحافظة)
    if dr_before >= trigger_threshold:
        reasons.append(ReasonCode.ROOT_ZONE_APPROACHING_RAW)
    if initial_depletion_mm > raw_mm:
        reasons.append(ReasonCode.ROOT_ZONE_BELOW_RAW)
    if is_critical:
        reasons.append(ReasonCode.CRITICAL_GROWTH_STAGE)
    if winner.stress_days:
        reasons.append(ReasonCode.STRESS_FORECAST)
    if winner.budget_exhausted:
        reasons.append(ReasonCode.WATER_BUDGET_LIMITED)
    if winner.total_deep_perc_mm > 0.0:
        reasons.append(ReasonCode.DEEP_PERCOLATION_RISK)
    if decision == "hold" and day0.eff_rain_mm > 0.0 and dr_after <= raw_mm:
        reasons.append(ReasonCode.RAIN_EXPECTED_HOLD)
    if state == OperatingState.DATA_DEGRADED:
        reasons.append(ReasonCode.DATA_DEGRADED)
    if not reasons:
        reasons.append(ReasonCode.NORMAL_SCHEDULE)

    # الثقة: قاعدة غير معايَرة، مخفوضة عند التدهور/انخفاض ثقة الاستنزاف.
    confidence = 0.7
    if state == OperatingState.DATA_DEGRADED:
        confidence = 0.4
    if depletion_confidence is not None:
        confidence = min(confidence, max(0.2, depletion_confidence))

    notes = ["مقابض/أوزان أوّليّة غير معايَرة يمنيّاً (calibrated=False)."]
    notes.append("الطاقة والآبار غير مُنمذَجة (not_modelled) — J2 ماء فقط، لا قيد طاقة.")
    if winner.budget_exhausted:
        notes.append("ميزانيّة الموسم قيّدت الخطّة الفائزة — راجِع التوزيع.")

    water_cost = obj.j4_water_cost if (water_price_per_m3 and water_price_per_m3 > 0) else None

    return LexicographicIrrigationDecision(
        decision=decision,
        field_id=field_id,
        operating_state=state,
        selected_policy=winner.policy,
        horizon_days=len(forecast),
        target_depth_mm=target_depth,
        predicted_water_m3_per_ha=target_depth * 10.0,
        root_zone_depletion_before_mm=dr_before,
        expected_root_zone_depletion_after_mm=dr_after,
        raw_mm=raw_mm,
        taw_mm=taw_mm,
        stress_risk_before=risk_before,
        stress_risk_after=risk_after,
        stress_days_in_horizon=winner.stress_days,
        yield_floor_preserved=yield_floor_preserved,
        yield_floor_basis="stress_proxy_pending_ky",
        water_cost_proxy=water_cost,
        economic_margin_delta=None,
        confidence=confidence,
        approval_required=True,
        reason_codes=reasons,
        objectives=obj,
        not_modelled=list(_NOT_MODELLED_PHASE0),
        calibrated=False,
        notes_ar=notes,
    )
