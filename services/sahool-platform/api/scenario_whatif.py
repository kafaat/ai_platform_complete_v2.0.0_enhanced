"""
api/scenario_whatif.py — محرّك سيناريوهات "ماذا لو" الفيزيائي

مُستلهَم من فكرة محاكاة "ماذا لو" في ورقة التوأم الرقمي (DSSAT/APSIM)، لكن
**مُكيّف بصدق جذري**: لا توأم رقمي، لا M2M، لا حسّاسات آنيّة، لا تعلّم عميق.
مجرّد **حساب فيزيائي بحت** يعيد استخدام نماذجنا الموجودة (ميزان الماء FAO-56
وGDD) للإجابة عن أسئلة قرار قبل التنفيذ:

  • "ماذا لو غيّرتُ تاريخ الزراعة؟" → أثر على تراكم GDD وبلوغ المراحل
  • "ماذا لو تغيّرت الحرارة (+2°)؟" → أثر على ET0 والاحتياج المائي
  • "ماذا لو قلّ المطر الموسمي؟" → أثر على صافي الريّ المطلوب

يلتقط أهمّ قيمة عمليّة في ورقة DT (الاستبصار المسبق لأثر القرارات) دون أيّ
من تعقيدها أو بنيتها التحتيّة المستحيلة. يعمل offline تماماً.

المبدأ: human-in-the-loop — يعرض المقارنة، والمزارع يقرّر. لا تنفيذ آلي.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.gdd_tracker import GDDResult
from api.water_balance import WeatherInput, water_balance


@dataclass
class ScenarioComparison:
    """مقارنة سيناريو أساس مقابل بديل."""

    metric_ar: str
    baseline: float
    scenario: float
    delta: float
    unit: str

    def to_dict(self) -> dict:
        return {
            "metric_ar": self.metric_ar,
            "baseline": round(self.baseline, 2),
            "scenario": round(self.scenario, 2),
            "delta": round(self.delta, 2),
            "unit": self.unit,
        }


def whatif_temperature_shift(
    w: WeatherInput,
    crop: str,
    stage: str,
    temp_shift_c: float,
    rain_mm: float = 0.0,
    *,
    base_et0_mm: float,
    scen_et0_mm: float,
    et0_method: str = "weather-engine",
) -> dict:
    """ماذا لو ارتفعت/انخفضت الحرارة بمقدار temp_shift_c؟

    يحسب أثر التغيّر على ET0 والاحتياج المائي الصافي (حساب فيزيائي بحت). WS-C.1b
    Zero-Legacy: ET0 للأساس والبديل (بالحرارة المُزاحة) محقونان من **محرّك الطقس**
    (المصدر الوحيد؛ لا نواة محلّيّة) — يجلبهما المُوجِّه async fail-closed.
    """
    base = water_balance(w, crop, stage, rain_mm=rain_mm, et0_mm=base_et0_mm, et0_method=et0_method)

    w2 = WeatherInput(
        t_min_c=w.t_min_c + temp_shift_c,
        t_max_c=w.t_max_c + temp_shift_c,
        solar_rad_mj_m2=w.solar_rad_mj_m2,
        rh_mean_pct=w.rh_mean_pct,
        wind_2m_ms=w.wind_2m_ms,
        latitude_deg=w.latitude_deg,
        elevation_m=w.elevation_m,
        day_of_year=w.day_of_year,
    )
    scen = water_balance(
        w2, crop, stage, rain_mm=rain_mm, et0_mm=scen_et0_mm, et0_method=et0_method
    )

    comparisons = [
        ScenarioComparison(
            "ET0 المرجعي", base.et0_mm, scen.et0_mm, scen.et0_mm - base.et0_mm, "مم/يوم"
        ),
        ScenarioComparison(
            "الاحتياج المائي الصافي",
            base.net_irrigation_mm,
            scen.net_irrigation_mm,
            scen.net_irrigation_mm - base.net_irrigation_mm,
            "مم",
        ),
    ]
    direction = "ارتفاع" if temp_shift_c > 0 else "انخفاض"
    pct = (
        (scen.net_irrigation_mm - base.net_irrigation_mm) / base.net_irrigation_mm * 100
        if base.net_irrigation_mm > 0
        else 0
    )
    summary = (
        f"{direction} الحرارة {abs(temp_shift_c)}° يغيّر الاحتياج المائي بـ"
        f"{pct:+.0f}٪ ({base.net_irrigation_mm:.1f} → {scen.net_irrigation_mm:.1f} مم). "
        "حساب فيزيائي — للاستبصار لا للتنفيذ الآلي."
    )
    return {
        "scenario_type": "temperature_shift",
        "comparisons": [c.to_dict() for c in comparisons],
        "summary_ar": summary,
    }


def whatif_planting_date(crop: str, base: GDDResult, scen: GDDResult) -> dict:
    """ماذا لو غيّرتُ تاريخ الزراعة؟ (سلسلة حرارة مختلفة من تاريخ مختلف).

    WS-C.1c Zero-Legacy: نواة GDD تُحسب في محرّك الطقس (لا ``track_gdd`` محلّيّ). يستقبل
    نتيجتَي GDD مُحقونتَين (``base``/``scen`` من تراكميّ المحرّك عبر ``stage_result_from_cumulative``)
    ويقارن التراكم وبلوغ المرحلة بين موعدَي زراعة — دالّة نقيّة (سياسة، لا حساب).
    """
    comparisons = [
        ScenarioComparison(
            "GDD المتراكم",
            base.cumulative_gdd,
            scen.cumulative_gdd,
            scen.cumulative_gdd - base.cumulative_gdd,
            "°C·يوم",
        ),
    ]
    if base.current_stage != scen.current_stage:
        stage_note = (
            f"اختلاف المرحلة: الأساس بلغ '{base.current_stage}'، "
            f"البديل بلغ '{scen.current_stage}' بعد {scen.days_counted} يوم."
        )
    else:
        stage_note = f"كلا الموعدَين عند مرحلة '{base.current_stage}'."

    summary = (
        f"تغيير الموعد يغيّر GDD المتراكم بـ"
        f"{scen.cumulative_gdd - base.cumulative_gdd:+.0f} °C·يوم. {stage_note} "
        "حساب فيزيائي offline — يساعد على اختيار الموعد، والقرار للمزارع."
    )
    return {
        "scenario_type": "planting_date",
        "comparisons": [c.to_dict() for c in comparisons],
        "baseline_stage": base.current_stage,
        "scenario_stage": scen.current_stage,
        "summary_ar": summary,
    }


def whatif_rainfall_change(
    w: WeatherInput,
    crop: str,
    stage: str,
    rain_baseline_mm: float,
    rain_scenario_mm: float,
    *,
    et0_mm: float,
    et0_method: str = "weather-engine",
) -> dict:
    """ماذا لو تغيّر المطر الموسمي؟ أثر على صافي الريّ المطلوب.

    WS-C.1b Zero-Legacy: نفس الطقس للأساس والبديل (يتغيّر المطر فقط) ⇒ ET0 واحد محقون
    من **محرّك الطقس** (المصدر الوحيد) يُمرَّر لكليهما — يجلبه المُوجِّه async fail-closed.
    """
    base = water_balance(
        w, crop, stage, rain_mm=rain_baseline_mm, et0_mm=et0_mm, et0_method=et0_method
    )
    scen = water_balance(
        w, crop, stage, rain_mm=rain_scenario_mm, et0_mm=et0_mm, et0_method=et0_method
    )

    comparisons = [
        ScenarioComparison(
            "المطر الفعّال",
            base.effective_rain_mm,
            scen.effective_rain_mm,
            scen.effective_rain_mm - base.effective_rain_mm,
            "مم",
        ),
        ScenarioComparison(
            "الاحتياج المائي الصافي",
            base.net_irrigation_mm,
            scen.net_irrigation_mm,
            scen.net_irrigation_mm - base.net_irrigation_mm,
            "مم",
        ),
    ]
    saved = base.net_irrigation_mm - scen.net_irrigation_mm
    summary = (
        f"تغيّر المطر من {rain_baseline_mm} إلى {rain_scenario_mm} مم "
        f"{'يوفّر' if saved > 0 else 'يزيد'} {abs(saved):.1f} مم ريّ. "
        "حساب فيزيائي للتخطيط الموسمي."
    )
    return {
        "scenario_type": "rainfall_change",
        "comparisons": [c.to_dict() for c in comparisons],
        "summary_ar": summary,
    }
