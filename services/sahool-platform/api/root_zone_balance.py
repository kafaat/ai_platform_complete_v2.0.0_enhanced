"""api/root_zone_balance.py — ميزان ماء منطقة الجذور عبر الزمن (FAO-56 Ch.8 / eq.85)

يسدّ فجوة «مركز المحاصيل»: water_balance يحسب احتياج **يوم واحد**؛ هنا نتتبّع
**استنزاف رطوبة منطقة الجذور Dr تراكميّاً عبر سلسلة أيّام**، ونُطلق الريّ حين يبلغ
الاستنزاف نسبة الاستنفاد المسموح بها RAW = p·TAW.

نقيّ حتميّ (لا I/O). يعيد استخدام _effective_rain (USDA-SCS) من water_balance.
صدق: human-in-the-loop افتراضيّاً (توصية لا ريّ آليّ)؛ الفيزياء FAO-56 معياريّة، لكن
TAW/p/عمق الجذور تقديريّة تحتاج معايرة يمنيّة (تُمرَّر من المستدعي).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.water_balance import _effective_rain


@dataclass
class DayInput:
    """مدخل يوم واحد لميزان منطقة الجذور."""

    et0_mm: float
    kc: float
    rain_mm: float = 0.0
    irrigation_mm: float = 0.0  # ريّ مُطبَّق فعلاً (صافٍ يصل الجذور)
    runoff_mm: float = 0.0  # جريان سطحيّ RO (قرار؛ افتراضه 0)


@dataclass
class DayBalance:
    day_index: int
    etc_mm: float
    eff_rain_mm: float
    dr_start_mm: float  # Dr_{i-1}
    dr_end_mm: float  # Dr_i بعد القصّ [0, TAW] (وبعد الريّ الآليّ إن فُعِّل)
    deep_perc_mm: float  # تسرّب عميق DP (فائض فوق السعة الحقليّة)
    irrigation_triggered: bool
    recommended_irrigation_mm: float  # = Dr عند الإطلاق، وإلّا 0

    def to_dict(self) -> dict:
        return {
            "day_index": self.day_index,
            "etc_mm": round(self.etc_mm, 2),
            "eff_rain_mm": round(self.eff_rain_mm, 2),
            "dr_start_mm": round(self.dr_start_mm, 2),
            "dr_end_mm": round(self.dr_end_mm, 2),
            "deep_perc_mm": round(self.deep_perc_mm, 2),
            "irrigation_triggered": self.irrigation_triggered,
            "recommended_irrigation_mm": round(self.recommended_irrigation_mm, 2),
        }


@dataclass
class RootZoneResult:
    taw_mm: float
    raw_mm: float
    days: list[DayBalance] = field(default_factory=list)
    trigger_days: list[int] = field(default_factory=list)
    total_recommended_irrigation_mm: float = 0.0
    final_depletion_mm: float = 0.0

    def to_dict(self) -> dict:
        return {
            "taw_mm": round(self.taw_mm, 2),
            "raw_mm": round(self.raw_mm, 2),
            "trigger_days": self.trigger_days,
            "total_recommended_irrigation_mm": round(self.total_recommended_irrigation_mm, 2),
            "final_depletion_mm": round(self.final_depletion_mm, 2),
            "days": [d.to_dict() for d in self.days],
        }


def root_zone_balance(
    days: list[DayInput],
    taw_mm: float,
    raw_fraction: float,
    initial_depletion_mm: float = 0.0,
    auto_irrigate: bool = False,
) -> RootZoneResult:
    """يتتبّع استنزاف منطقة الجذور Dr يوميّاً (FAO-56 eq.85) — نقيّ حتميّ.

    Dr_i = Dr_{i-1} − (مطر فعّال − جريان) − ريّ + ETc، مقصوصة في [0, TAW].
    الفائض فوق السعة الحقليّة (Dr<0) ⇒ تسرّب عميق DP. الإطلاق حين Dr ≥ RAW=p·TAW،
    والكمّيّة الموصى بها = Dr (تملأ الاستنزاف). auto_irrigate=True يحاكي جدول ريّ
    حتميّاً (يملأ Dr عند الإطلاق)؛ False = توصية فقط (Dr يتراكم).
    """
    raw_mm = raw_fraction * taw_mm
    dr_prev = initial_depletion_mm
    out: list[DayBalance] = []
    triggers: list[int] = []
    total_rec = 0.0

    for i, day in enumerate(days):
        etc = day.et0_mm * day.kc
        eff_rain = _effective_rain(day.rain_mm)
        dr_raw = dr_prev - (eff_rain - day.runoff_mm) - day.irrigation_mm + etc
        if dr_raw < 0.0:
            deep_perc = -dr_raw
            dr_end = 0.0
        else:
            deep_perc = 0.0
            dr_end = min(dr_raw, taw_mm)

        triggered = dr_end >= raw_mm
        recommended = dr_end if triggered else 0.0
        if triggered:
            triggers.append(i)
            total_rec += recommended
        if auto_irrigate and triggered:
            dr_end = 0.0  # طُبِّق الريّ الموصى به ⇒ يبدأ اليوم التالي من السعة الحقليّة

        out.append(
            DayBalance(
                day_index=i,
                etc_mm=etc,
                eff_rain_mm=eff_rain,
                dr_start_mm=dr_prev,
                dr_end_mm=dr_end,
                deep_perc_mm=deep_perc,
                irrigation_triggered=triggered,
                recommended_irrigation_mm=recommended,
            )
        )
        dr_prev = dr_end

    return RootZoneResult(
        taw_mm=taw_mm,
        raw_mm=raw_mm,
        days=out,
        trigger_days=triggers,
        total_recommended_irrigation_mm=total_rec,
        final_depletion_mm=dr_prev,
    )
