"""api/lexicographic_irrigation_mpc.py — متحكّم تنبّؤيّ هرميّ معجميّ للريّ (Lexicographic MPC)

يُعمّم المُخطِّط الجشِع `api/irrigation_mpc.plan_irrigation` من **سياسة واحدة** إلى
**اختيار معجميّ (lexicographic)** بين خطط مرشَّحة، وفق سلّم أولويّات صارم غير قابل
للمقايضة الماليّة:

  الأولوية 1 (J1): حماية المحصول من الإجهاد الحرج  — Dr ≤ RAW + أيّام إجهاد مُثقَّلة
                    بحسّاسيّة المرحلة.
  الأولوية 2 (J2): تقليل استهلاك الماء (والطاقة)   — ماء مُطبَّق + رشح عميق. الطاقة
                    **غير مُنمذَجة** (لا بيانات آبار/مضخّات/شمسيّة) — `not_modelled`.
  الأولوية 3 (J3): الحفاظ على حدّ إنتاج أدنى        — **المرحلة 1:** نموذج Ky الكنسيّ
                    `Ya/Ym = 1 − Ky·(1 − ETa/ETm)` (FAO-33)؛ Ky حسب المحصول والمرحلة من
                    `core/engines/ky_registry` (لا اختلاق). غياب Ky/المرحلة ⇒
                    `insufficient_data` بلا استبدال صامت.
  الأولوية 4 (J4): تعظيم الهامش الاقتصاديّ          — وكيل تكلفة ماء ($/m³). الإيراد
                    والطاقة `not_modelled`. **لا يُشتَقّ أيّ هامش/إيراد من Ky** (يفصله
                    حارس CI حتى وصول نموذج اقتصاديّ صريح).

الاختيار المعجميّ بهامش ε: نُثبّت أفضل J1، ثمّ ضمن الهامش أفضل J2، ثمّ J3، ثمّ J4 — لا
يُسمح لمستوى أدنى بتحسين نتيجته إن أضرّ بمستوى أعلى (حماية المحصول لا تُكسَر لأجل الغلّة).

نقيّ حتميّ (لا I/O، لا شبكة، لا عشوائيّة). **توصية-فقط**: `approval_required=True` دائماً؛
لا أمر مضخّة مباشر — يُصدِر مرشّح قرار محكوماً يمرّ بمركز القرار. لا يمسّ التنفيذ/MQTT/
التفويض. المقابض/الأوزان أوّليّة (`calibrated=False`) تحتاج معايرة يمنيّة.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum

# سجلّ Ky الكنسيّ (FAO-33) — المصدر الموثَّق الوحيد لمعاملات استجابة الغلّة.
from core.engines.ky_registry import KY_REGISTRY_VERSION, KyLookup, lookup_ky

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
EPS_J3 = 1e-4  # هامش سماح J3 (كسر غلّة)
WATER_WASTE_PENALTY = 1.0  # وزن الرشح العميق ضمن J2 (مم لكلّ مم)

# مجموعة السياسات المرشَّحة (فضاء القرار المُنفصِل الحتميّ) — كلّ الخمس القائمة.
_CANDIDATE_POLICIES: tuple[IrrigationPolicy, ...] = (
    IrrigationPolicy.RISK_AVERSE,
    IrrigationPolicy.YIELD_MAX,
    IrrigationPolicy.PROFIT_MAX,
    IrrigationPolicy.WATER_SAVING,
    IrrigationPolicy.SUSTAINABILITY,
)

# الحقول المُؤجَّلة صراحةً (تُعلَن ولا تُلفَّق).
_NOT_MODELLED: tuple[str, ...] = (
    "predicted_energy_kwh",  # يحتاج طبقة الطاقة/المضخّة (المرحلة 2)
    "source_well_id",  # يحتاج نموذج الآبار (المرحلة 2)
    "start_at",  # يحتاج أفقاً ساعيّاً (المرحلة 3)
    "duration_minutes",  # يحتاج معدّل تطبيق/تدفّق (المرحلة 3)
    "zone_id",  # يحتاج قراراً على مستوى المناطق (لاحقاً)
    "economic_margin_delta.revenue",  # الإيراد غير مُنمذَج (وكيل تكلفة فقط؛ لا يُشتَقّ من Ky)
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
    YIELD_FLOOR_AT_RISK = "YIELD_FLOOR_AT_RISK"  # الغلّة المتوقّعة دون حدّ الإنتاج
    YIELD_DATA_INSUFFICIENT = "YIELD_DATA_INSUFFICIENT"  # لا Ky/مرحلة/ETa-ETm ⇒ J3 غير محسوب
    NORMAL_SCHEDULE = "NORMAL_SCHEDULE"
    DATA_DEGRADED = "DATA_DEGRADED"
    MISSING_CRITICAL_INPUTS = "MISSING_CRITICAL_INPUTS"


class OperatingState(str, Enum):
    """حالات التشغيل — تحدّد أيّ منطق يقود القرار."""

    NORMAL_OPTIMIZATION = "NORMAL_OPTIMIZATION"
    CROP_PROTECTION = "CROP_PROTECTION"
    WATER_SCARCITY = "WATER_SCARCITY"
    ENERGY_CONSTRAINED = "ENERGY_CONSTRAINED"  # غير قابلة للوصول قبل طبقة الطاقة (المرحلة 2)
    DATA_DEGRADED = "DATA_DEGRADED"
    EMERGENCY_FAIL_CLOSED = "EMERGENCY_FAIL_CLOSED"


@dataclass
class YieldResponse:
    """مخرَج نموذج Ky لخطّة (J3) — Ya/Ym = 1 − Ky·(1 − ETa/ETm)."""

    status: str  # "ok" | "insufficient_data" | "out_of_bounds"
    eta_over_etm: float | None
    ky: float | None
    ky_source: str | None
    ky_basis: str | None  # "crop_stage" | "generic_stage"
    predicted_relative_yield: float | None  # Ya/Ym مقصوص [0,1]
    predicted_yield_loss_fraction: float | None  # 1 − Ya/Ym
    within_bounds: bool
    uncertainty: float | None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "eta_over_etm": None if self.eta_over_etm is None else round(self.eta_over_etm, 4),
            "ky": self.ky,
            "ky_source": self.ky_source,
            "ky_basis": self.ky_basis,
            "predicted_relative_yield": (
                None
                if self.predicted_relative_yield is None
                else round(self.predicted_relative_yield, 4)
            ),
            "predicted_yield_loss_fraction": (
                None
                if self.predicted_yield_loss_fraction is None
                else round(self.predicted_yield_loss_fraction, 4)
            ),
            "within_bounds": self.within_bounds,
            "uncertainty": self.uncertainty,
        }


@dataclass
class LexObjectives:
    """قيم الأهداف الأربعة لخطّة مرشَّحة (كلّها «أقلّ أفضل»)."""

    j1_crop_protection: float
    j2_water: float
    j3_yield_loss: float  # كسر الغلّة (Ky)؛ 0 محايد عند insufficient_data
    j4_water_cost: float
    j3_status: str = "insufficient_data"
    energy_modelled: bool = False  # J2 يشمل الطاقة؟ (لا حتى المرحلة 2)

    def to_dict(self) -> dict:
        return {
            "j1_crop_protection": round(self.j1_crop_protection, 4),
            "j2_water": round(self.j2_water, 4),
            "j3_yield_loss": round(self.j3_yield_loss, 6),
            "j3_status": self.j3_status,
            "j4_water_cost": round(self.j4_water_cost, 4),
            "energy_modelled": self.energy_modelled,
        }


@dataclass
class LexicographicIrrigationDecision:
    """قرار الريّ المعجميّ — عقد المتحكّم (توصية-فقط)."""

    decision: str  # "irrigate" | "hold"
    field_id: str | None
    crop: str | None
    growth_stage: str | None
    operating_state: OperatingState
    selected_policy: str | None
    horizon_days: int
    target_depth_mm: float
    predicted_water_m3_per_ha: float
    root_zone_depletion_before_mm: float
    expected_root_zone_depletion_after_mm: float
    raw_mm: float
    taw_mm: float
    stress_risk_before: str
    stress_risk_after: str
    stress_days_in_horizon: list[int]
    # ── J3 نموذج Ky ──
    yield_response: YieldResponse
    yield_floor_ratio: float | None
    yield_floor_preserved: bool | None  # None = لا يمكن التأكيد (بيانات ناقصة أو لا هدف)
    # ── اقتصاد (وكيل) ──
    water_cost_proxy: float | None
    economic_margin_delta: float | None  # None (لا إيراد؛ لا يُشتَقّ من Ky)
    confidence: float
    approval_required: bool  # True دائماً
    reason_codes: list[ReasonCode]
    objectives: LexObjectives | None
    objective_trace: dict = field(default_factory=dict)
    candidate_lineage_id: str = ""
    not_modelled: list[str] = field(default_factory=list)
    calibrated: bool = False
    notes_ar: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "field_id": self.field_id,
            "crop": self.crop,
            "growth_stage": self.growth_stage,
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
            "yield_response": self.yield_response.to_dict(),
            "yield_floor_ratio": self.yield_floor_ratio,
            "yield_floor_preserved": self.yield_floor_preserved,
            "water_cost_proxy": (
                None if self.water_cost_proxy is None else round(self.water_cost_proxy, 4)
            ),
            "economic_margin_delta": self.economic_margin_delta,
            "confidence": round(self.confidence, 3),
            "approval_required": self.approval_required,
            "reason_codes": [c.value for c in self.reason_codes],
            "objectives": None if self.objectives is None else self.objectives.to_dict(),
            "objective_trace": self.objective_trace,
            "candidate_lineage_id": self.candidate_lineage_id,
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


def _eta_over_etm(plan: IrrigationPlan) -> float | None:
    """نسبة النتح الفعليّ للأقصى ETa/ETm عبر الأفق من Ks اليوميّ (FAO-56).

    Ks = 1 حين Dr ≤ RAW، وإلّا (TAW−Dr)/(TAW−RAW) مقصوصاً [0,1]. يعيد None إن كان ETm
    غير صالح (≤0 أو غير منتهٍ) — يعامله المتحكّم كـ insufficient_data.
    """
    etm = 0.0
    for d in plan.days:
        if not math.isfinite(d.etc_mm):
            return None
        etm += d.etc_mm
    if etm <= 0.0 or not math.isfinite(etm):
        return None
    denom = plan.taw_mm - plan.raw_mm
    eta = 0.0
    for d in plan.days:
        if denom <= 0.0:
            ks = 1.0 if d.dr_end_mm <= plan.raw_mm else 0.0
        elif d.dr_end_mm <= plan.raw_mm:
            ks = 1.0
        else:
            ks = max(0.0, min(1.0, (plan.taw_mm - d.dr_end_mm) / denom))
        eta += ks * d.etc_mm
    ratio = eta / etm
    if not math.isfinite(ratio):
        return None
    return max(0.0, min(1.0, ratio))


def _yield_response(plan: IrrigationPlan, ky_lookup: KyLookup | None) -> YieldResponse:
    """يطبّق نموذج Ky الكنسيّ على خطّة — J3 = كسر الغلّة المتوقّع."""
    if ky_lookup is None:
        return YieldResponse(
            status="insufficient_data",
            eta_over_etm=None,
            ky=None,
            ky_source=None,
            ky_basis=None,
            predicted_relative_yield=None,
            predicted_yield_loss_fraction=None,
            within_bounds=False,
            uncertainty=None,
        )
    ratio = _eta_over_etm(plan)
    if ratio is None:
        # ETm غير صالح (لا طلب تبخّر-نتحيّ) ⇒ لا نسبة ⇒ insufficient_data (بلا اختلاق).
        return YieldResponse(
            status="insufficient_data",
            eta_over_etm=None,
            ky=ky_lookup.ky,
            ky_source=ky_lookup.ky_source,
            ky_basis=ky_lookup.ky_basis,
            predicted_relative_yield=None,
            predicted_yield_loss_fraction=None,
            within_bounds=False,
            uncertainty=ky_lookup.uncertainty,
        )
    ky = ky_lookup.ky
    ry_raw = 1.0 - ky * (1.0 - ratio)
    within = ry_raw >= 0.0  # النموذج الخطّيّ يفقد صلاحيّته عند عجز شديد (Ky>1)
    ry = max(0.0, min(1.0, ry_raw))
    loss = 1.0 - ry
    return YieldResponse(
        status="ok" if within else "out_of_bounds",
        eta_over_etm=ratio,
        ky=ky,
        ky_source=ky_lookup.ky_source,
        ky_basis=ky_lookup.ky_basis,
        predicted_relative_yield=ry,
        predicted_yield_loss_fraction=loss,
        within_bounds=within,
        uncertainty=ky_lookup.uncertainty,
    )


def _score_plan(
    plan: IrrigationPlan,
    is_critical_stage: bool,
    water_price_per_m3: float | None,
    ky_lookup: KyLookup | None,
) -> tuple[LexObjectives, YieldResponse]:
    """يسجّل خطّة على الأهداف الأربعة — كلّها «أقلّ أفضل»."""
    raw = plan.raw_mm
    j1 = 0.0
    for d in plan.days:
        over = max(0.0, d.dr_end_mm - raw)
        j1 += over * over  # مربّع تجاوز RAW (يعاقب الإجهاد بشدّة)
        if d.stressed and is_critical_stage:
            j1 += LAMBDA_STRESS

    j2 = plan.total_irrigation_mm + WATER_WASTE_PENALTY * plan.total_deep_perc_mm

    yr = _yield_response(plan, ky_lookup)
    # J3 = كسر الغلّة (Ky) حين يُحسَب؛ 0 محايد عند insufficient_data (لا يرجّح شيئاً).
    j3 = yr.predicted_yield_loss_fraction if yr.status in ("ok", "out_of_bounds") else 0.0

    # J4 وكيل تكلفة الماء (الإيراد/الطاقة غير مُنمذَجَين؛ **لا يُشتَقّ من Ky**).
    price = water_price_per_m3 if water_price_per_m3 and water_price_per_m3 > 0 else 0.0
    j4 = plan.total_irrigation_m3_ha * price
    return (
        LexObjectives(
            j1_crop_protection=j1,
            j2_water=j2,
            j3_yield_loss=j3 or 0.0,
            j4_water_cost=j4,
            j3_status=yr.status,
            energy_modelled=False,
        ),
        yr,
    )


def _lexicographic_select(
    scored: list[tuple[IrrigationPlan, LexObjectives, YieldResponse]],
) -> tuple[IrrigationPlan, LexObjectives, YieldResponse, int]:
    """اختيار معجميّ بهامش ε: J1 ثمّ J2 ثمّ J3 ثمّ J4. يعيد أعلى مستوى حسم الاختيار."""
    best_j1 = min(s.j1_crop_protection for _, s, _ in scored)
    s1 = [t for t in scored if t[1].j1_crop_protection <= best_j1 + EPS_J1]
    level = 1 if len(s1) < len(scored) else 0

    best_j2 = min(t[1].j2_water for t in s1)
    s2 = [t for t in s1 if t[1].j2_water <= best_j2 + EPS_J2_MM]
    if len(s2) < len(s1):
        level = 2

    best_j3 = min(t[1].j3_yield_loss for t in s2)
    s3 = [t for t in s2 if t[1].j3_yield_loss <= best_j3 + EPS_J3]
    if len(s3) < len(s2):
        level = 3

    winner = min(s3, key=lambda t: t[1].j4_water_cost)
    if len(s3) > 1:
        level = max(level, 4)
    return winner[0], winner[1], winner[2], level


def _lineage_id(payload: str) -> str:
    return "mpc_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _emergency_decision(
    field_id: str | None,
    crop: str | None,
    growth_stage: str | None,
    reason: ReasonCode,
    note_ar: str,
) -> LexicographicIrrigationDecision:
    """قرار فاشل-مُغلَق محافظ: لا أمر تنفيذ، موافقة بشريّة، ثقة دنيا."""
    yr = YieldResponse("insufficient_data", None, None, None, None, None, None, False, None)
    return LexicographicIrrigationDecision(
        decision="hold",
        field_id=field_id,
        crop=crop,
        growth_stage=growth_stage,
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
        yield_response=yr,
        yield_floor_ratio=None,
        yield_floor_preserved=None,
        water_cost_proxy=None,
        economic_margin_delta=None,
        confidence=0.0,
        approval_required=True,
        reason_codes=[reason],
        objectives=None,
        objective_trace={},
        candidate_lineage_id="",
        not_modelled=list(_NOT_MODELLED),
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
    crop: str | None = None,
    growth_stage: str | None = None,
    yield_floor_ratio: float | None = None,
    max_application_mm: float | None = None,
    season_budget_mm: float | None = None,
    water_price_per_m3: float | None = None,
    depletion_confidence: float | None = None,
    data_degraded: bool = False,
) -> LexicographicIrrigationDecision:
    """يحلّ قرار الريّ معجميّاً على أفق يوميّ — نقيّ حتميّ، توصية-فقط.

    J3 = نموذج Ky الكنسيّ (FAO-33) حسب المحصول والمرحلة؛ غياب Ky/المرحلة ⇒ insufficient_data
    (لا استبدال صامت). `yield_floor_preserved` لا يصير True إلّا مع بيانات كاملة (ETa/ETm
    صالحان + مرحلة معروفة + Ky متاح + داخل حدود النموذج + هدف حدّ إنتاج مُمرَّر ومُحقَّق).
    """
    if not forecast:
        return _emergency_decision(
            field_id,
            crop,
            growth_stage,
            ReasonCode.MISSING_CRITICAL_INPUTS,
            "لا أفق تنبّؤ — لا قرار ريّ ممكن",
        )
    if taw_mm <= 0.0 or not (0.0 < raw_fraction <= 1.0):
        return _emergency_decision(
            field_id,
            crop,
            growth_stage,
            ReasonCode.MISSING_CRITICAL_INPUTS,
            "TAW/RAW غير صالح — فشل مُغلَق",
        )

    raw_mm = raw_fraction * taw_mm
    ky_lookup = lookup_ky(crop, growth_stage)
    is_critical = ky_lookup is not None and ky_lookup.ky >= CRITICAL_STAGE_KY

    scored: list[tuple[IrrigationPlan, LexObjectives, YieldResponse]] = []
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
        obj, yr = _score_plan(plan, is_critical, water_price_per_m3, ky_lookup)
        scored.append((plan, obj, yr))

    winner, obj, yr, decided_level = _lexicographic_select(scored)

    day0 = winner.days[0]
    target_depth = day0.irrigation_mm
    dr_before = day0.dr_before_irrig_mm
    dr_after = day0.dr_end_mm
    decision = "irrigate" if target_depth > 0.0 else "hold"

    risk_before = _risk_class(initial_depletion_mm, taw_mm, raw_fraction)
    risk_after = _risk_class(dr_after, taw_mm, raw_fraction)

    # حدّ الإنتاج: يُحفَظ فقط ببيانات كاملة (Ky/مرحلة/ETa-ETm/داخل الحدود) + هدف مُحقَّق.
    if yr.status != "ok" or yr.predicted_relative_yield is None:
        yield_floor_preserved: bool | None = None
    elif yield_floor_ratio is None:
        yield_floor_preserved = None  # لا هدف حدّ إنتاج ⇒ لا تأكيد
    else:
        yield_floor_preserved = yr.predicted_relative_yield >= yield_floor_ratio

    approaching_critical = dr_before >= raw_mm or risk_before in ("watch", "critical")
    if winner.budget_exhausted and winner.stress_days:
        state = OperatingState.WATER_SCARCITY
    elif is_critical and (approaching_critical or winner.stress_days):
        state = OperatingState.CROP_PROTECTION
    elif data_degraded or (depletion_confidence is not None and depletion_confidence < 0.5):
        state = OperatingState.DATA_DEGRADED
    else:
        state = OperatingState.NORMAL_OPTIMIZATION

    reasons: list[ReasonCode] = []
    if dr_before >= raw_mm:
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
    if yr.status == "insufficient_data":
        reasons.append(ReasonCode.YIELD_DATA_INSUFFICIENT)
    elif yield_floor_preserved is False:
        reasons.append(ReasonCode.YIELD_FLOOR_AT_RISK)
    if state == OperatingState.DATA_DEGRADED:
        reasons.append(ReasonCode.DATA_DEGRADED)
    if not reasons:
        reasons.append(ReasonCode.NORMAL_SCHEDULE)

    # الثقة: قاعدة غير معايَرة، مخفوضة لأساس Ky العامّ/خارج الحدود/عدم يقين Ky/التدهور.
    confidence = 0.7
    if yr.ky_basis == "generic_stage":
        confidence *= 0.85
    if yr.status == "out_of_bounds":
        confidence *= 0.8
    if yr.uncertainty is not None:
        confidence *= 1.0 - min(0.3, yr.uncertainty)
    if state == OperatingState.DATA_DEGRADED:
        confidence = min(confidence, 0.4)
    if depletion_confidence is not None:
        confidence = min(confidence, max(0.2, depletion_confidence))

    notes = [
        "مقابض/أوزان أوّليّة غير معايَرة يمنيّاً (calibrated=False).",
        "الطاقة والآبار غير مُنمذَجة (not_modelled) — J2 ماء فقط، لا قيد طاقة.",
    ]
    if yr.ky_basis == "generic_stage":
        notes.append("Ky عامّ حسب المرحلة (FAO-33) — لا قيمة خاصّة بالمحصول؛ ثقة أدنى.")
    if yr.status == "insufficient_data":
        notes.append("J3 غير محسوب (لا Ky/مرحلة أو ETm غير صالح) — حدّ الإنتاج غير مُؤكَّد.")
    if yr.status == "out_of_bounds":
        notes.append("عجز شديد يتجاوز حدود نموذج Ky الخطّيّ — الغلّة النسبيّة مقصوصة.")
    if winner.budget_exhausted:
        notes.append("ميزانيّة الموسم قيّدت الخطّة الفائزة — راجِع التوزيع.")

    water_cost = obj.j4_water_cost if (water_price_per_m3 and water_price_per_m3 > 0) else None

    objective_trace = {
        "decided_at_level": decided_level,  # 1..4، أعلى مستوى حسم الاختيار
        "j1_crop_protection": round(obj.j1_crop_protection, 4),
        "j2_water": round(obj.j2_water, 4),
        "j3_yield_loss": round(obj.j3_yield_loss, 6),
        "j3_status": obj.j3_status,
        "j4_water_cost": round(obj.j4_water_cost, 4),
        "ky": yr.ky,
        "ky_source": yr.ky_source,
        "ky_basis": yr.ky_basis,
        "ky_registry_version": KY_REGISTRY_VERSION,
        "eta_over_etm": None if yr.eta_over_etm is None else round(yr.eta_over_etm, 4),
        "predicted_relative_yield": yr.predicted_relative_yield,
        "yield_floor_ratio": yield_floor_ratio,
    }

    lineage = _lineage_id(
        "|".join(
            str(x)
            for x in (
                field_id,
                crop,
                growth_stage,
                round(taw_mm, 3),
                round(raw_fraction, 3),
                round(initial_depletion_mm, 3),
                yield_floor_ratio,
                KY_REGISTRY_VERSION,
                [(round(d.et0_mm, 3), round(d.kc, 3), round(d.rain_mm, 3)) for d in forecast],
            )
        )
    )

    return LexicographicIrrigationDecision(
        decision=decision,
        field_id=field_id,
        crop=crop,
        growth_stage=growth_stage,
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
        yield_response=yr,
        yield_floor_ratio=yield_floor_ratio,
        yield_floor_preserved=yield_floor_preserved,
        water_cost_proxy=water_cost,
        economic_margin_delta=None,
        confidence=confidence,
        approval_required=True,
        reason_codes=reasons,
        objectives=obj,
        objective_trace=objective_trace,
        candidate_lineage_id=lineage,
        not_modelled=list(_NOT_MODELLED),
        calibrated=False,
        notes_ar=notes,
    )
