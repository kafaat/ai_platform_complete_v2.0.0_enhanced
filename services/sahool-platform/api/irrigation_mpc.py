"""api/irrigation_mpc.py — مُخطِّط الريّ التنبّؤيّ بالأفق المتحرّك (#376، MPC)

الطبقة الخامسة (القمّة) في خطّ «مركز المحاصيل»: يخطّط جدول الريّ للأيّام القادمة
بمحاكاة نموذج النبات (root_zone_balance) أماماً عبر أفق التنبّؤ الجوّيّ، وفق السياسة
المختارة (irrigation_policy). الريّ هنا **متغيّر القرار** لا مُدخَل.

المنطق (متحكّم جشِع بأفق متحرّك، حتميّ):
  لكلّ يوم في الأفق:
    Dr يتراكم طبيعيّاً = Dr_{i-1} − (مطر فعّال − جريان) + ETc، مقصوص [0, TAW]؛
    حين Dr ≥ trigger_fraction·RAW ⇒ نطبّق ريّاً = refill_fraction·Dr، مقيَّداً بسقف
    الدفعة وميزانيّة الموسم؛ نخصمه من Dr. نتتبّع الإجهاد (Dr > RAW) والتسرّب العميق.

ليس مُحسِّناً عامّاً (QP/LP) بل متحكّم شفّاف قابل للتفسير فوق فيزياء FAO-56 —
كافٍ للجدولة العمليّة، وصادق (لا يدّعي أمثليّة عالميّة). نقيّ حتميّ، يعيد استخدام
_effective_rain. القيود (سقف الدفعة/الميزانيّة) تُمرَّر من المستخدم.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.irrigation_policy import IrrigationPolicy, PolicyParams, policy_params
from api.water_balance import _effective_rain


@dataclass
class ForecastDay:
    """يوم في أفق التنبّؤ: طقس/طلب فقط — الريّ قرار المتحكّم."""

    et0_mm: float
    kc: float
    rain_mm: float = 0.0
    runoff_mm: float = 0.0


@dataclass
class PlannedDay:
    day_index: int
    etc_mm: float
    eff_rain_mm: float
    dr_before_irrig_mm: float
    irrigation_mm: float
    dr_end_mm: float
    deep_perc_mm: float
    stressed: bool  # Dr بعد الريّ ما يزال > RAW

    def to_dict(self) -> dict:
        return {
            "day_index": self.day_index,
            "etc_mm": round(self.etc_mm, 2),
            "eff_rain_mm": round(self.eff_rain_mm, 2),
            "dr_before_irrig_mm": round(self.dr_before_irrig_mm, 2),
            "irrigation_mm": round(self.irrigation_mm, 2),
            "dr_end_mm": round(self.dr_end_mm, 2),
            "deep_perc_mm": round(self.deep_perc_mm, 2),
            "stressed": self.stressed,
        }


@dataclass
class IrrigationPlan:
    policy: str
    taw_mm: float
    raw_mm: float
    days: list[PlannedDay] = field(default_factory=list)
    total_irrigation_mm: float = 0.0
    total_irrigation_m3_ha: float = 0.0
    n_events: int = 0
    stress_days: list[int] = field(default_factory=list)
    total_deep_perc_mm: float = 0.0
    final_depletion_mm: float = 0.0
    budget_exhausted: bool = False
    calibrated: bool = False
    notes_ar: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "policy": self.policy,
            "taw_mm": round(self.taw_mm, 2),
            "raw_mm": round(self.raw_mm, 2),
            "total_irrigation_mm": round(self.total_irrigation_mm, 2),
            "total_irrigation_m3_ha": round(self.total_irrigation_m3_ha, 2),
            "n_events": self.n_events,
            "stress_days": self.stress_days,
            "total_deep_perc_mm": round(self.total_deep_perc_mm, 2),
            "final_depletion_mm": round(self.final_depletion_mm, 2),
            "budget_exhausted": self.budget_exhausted,
            "calibrated": self.calibrated,
            "notes_ar": self.notes_ar,
            "days": [d.to_dict() for d in self.days],
        }


def plan_irrigation(
    forecast: list[ForecastDay],
    taw_mm: float,
    raw_fraction: float,
    policy: IrrigationPolicy | str | PolicyParams = IrrigationPolicy.WATER_SAVING,
    initial_depletion_mm: float = 0.0,
    max_application_mm: float | None = None,
    season_budget_mm: float | None = None,
    water_price_per_m3: float | None = None,
    yield_value_per_ha: float | None = None,
) -> IrrigationPlan:
    """يخطّط جدول الريّ عبر أفق التنبّؤ وفق السياسة — نقيّ حتميّ.

    القيود الاختياريّة: max_application_mm (سقف الدفعة)، season_budget_mm (ميزانيّة
    الموسم). عند نفاد الميزانيّة نتوقّف عن الريّ (budget_exhausted) — لا نتجاوزها.
    """
    pp = (
        policy
        if isinstance(policy, PolicyParams)
        else policy_params(policy, water_price_per_m3, yield_value_per_ha)
    )
    raw_mm = raw_fraction * taw_mm
    trigger_threshold = pp.trigger_fraction * raw_mm

    dr = initial_depletion_mm
    out: list[PlannedDay] = []
    stress_days: list[int] = []
    total_irrig = 0.0
    total_dp = 0.0
    n_events = 0
    budget_left = season_budget_mm
    budget_exhausted = False

    for i, day in enumerate(forecast):
        etc = day.et0_mm * day.kc
        eff_rain = _effective_rain(day.rain_mm)
        dr_raw = dr - (eff_rain - day.runoff_mm) + etc
        if dr_raw < 0.0:
            deep_perc = -dr_raw
            dr_before = 0.0
        else:
            deep_perc = 0.0
            dr_before = min(dr_raw, taw_mm)
        total_dp += deep_perc

        irrig = 0.0
        if dr_before >= trigger_threshold and trigger_threshold >= 0:
            target = pp.refill_fraction * dr_before
            if max_application_mm is not None:
                target = min(target, max_application_mm)
            if budget_left is not None:
                if budget_left <= 0.0:
                    target = 0.0
                    budget_exhausted = True
                else:
                    target = min(target, budget_left)
            if target > 0.0:
                irrig = target
                dr_before_irrig_record = dr_before
                dr_end = max(0.0, dr_before - irrig)
                total_irrig += irrig
                n_events += 1
                if budget_left is not None:
                    budget_left -= irrig
            else:
                dr_before_irrig_record = dr_before
                dr_end = dr_before
        else:
            dr_before_irrig_record = dr_before
            dr_end = dr_before

        stressed = dr_end > raw_mm
        if stressed:
            stress_days.append(i)

        out.append(
            PlannedDay(
                day_index=i,
                etc_mm=etc,
                eff_rain_mm=eff_rain,
                dr_before_irrig_mm=dr_before_irrig_record,
                irrigation_mm=irrig,
                dr_end_mm=dr_end,
                deep_perc_mm=deep_perc,
                stressed=stressed,
            )
        )
        dr = dr_end

    notes = list(pp.notes_ar)
    if budget_exhausted:
        notes.append("نفدت ميزانيّة الموسم — توقّف الريّ رغم الحاجة (راجِع الميزانيّة)")

    return IrrigationPlan(
        policy=pp.policy.value,
        taw_mm=taw_mm,
        raw_mm=raw_mm,
        days=out,
        total_irrigation_mm=total_irrig,
        total_irrigation_m3_ha=total_irrig * 10.0,  # 1 مم = 10 م³/هكتار
        n_events=n_events,
        stress_days=stress_days,
        total_deep_perc_mm=total_dp,
        final_depletion_mm=dr,
        budget_exhausted=budget_exhausted,
        notes_ar=notes,
    )
