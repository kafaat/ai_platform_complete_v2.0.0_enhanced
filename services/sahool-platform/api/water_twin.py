"""api/water_twin.py — توأم المياه: محاكاة مسار رطوبة التربة الأماميّ (Water Twin)

يكمّل ``scenario_whatif.py`` (الذي يجيب أسئلة يوم-واحد: حرارة/مطر/موعد زراعة) بإضافة
**المسار الزمنيّ متعدّد الأيّام لنضوب منطقة الجذور** — جوهر فكرة Water Twin من إلهام IrriPro
(``decisions/water-intelligence-direction.md``): «ماذا لو أخّرتُ الريّ ٣ أيّام؟ خفّضتُه ٢٠٪؟»
→ أثر مباشر على رطوبة التربة وأيّام الإجهاد واستهلاك الماء.

**صدق جذريّ:**
  - **حساب فيزيائيّ بحت** (ميزان ماء FAO-56، فصل ٨) — لا توأم رقميّ كامل، لا M2M، لا ML.
  - يحاكي **نضوب الجذور (Dr)** يوماً بيوم مع تخفيض ET الفعليّ تحت الإجهاد (ETa = Ks·ETc).
  - **لا يدّعي إنتاجاً/غلّة** (لا نملك نموذج غلّة مُعايَر) — المخرَج الزراعيّ هو **أيّام الإجهاد**
    ونضوب الجذور واستهلاك الماء فقط (مؤشّرات صادقة قابلة للتحقّق). ربط الغلّة TODO موثَّق.
  - human-in-the-loop: يعرض المقارنة، والمزارع يقرّر. لا تنفيذ آليّ.
  - نقيّ (لا I/O، لا قاعدة) ⇒ يُختبَر بـunit ويعمل offline تماماً.

يُغذّى مبدئيّاً بحالة التربة من **دفتر المياه اليوميّ** (v98) أو بمدخلات صريحة؛ هذا الملفّ يبقى
نقيّاً (الحالة تُمرَّر إليه)، فيبقى مصدر الحقيقة الوحيد للحساب الفيزيائيّ.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DayPlan:
    """خطّة يوم واحد: تبخّر-نتح المحصول + مطر فعّال + ريّ مُطبَّق (مم)."""

    etc_mm: float  # ETc المحتمَل (بلا إجهاد) لليوم
    rain_mm: float = 0.0  # مطر فعّال يدخل منطقة الجذور
    irrigation_mm: float = 0.0  # عمق الريّ المُطبَّق


@dataclass
class DayState:
    """حالة التربة المحسوبة بنهاية اليوم."""

    day: int  # رقم اليوم (1-مفهرس)
    depletion_mm: float  # نضوب منطقة الجذور Dr بنهاية اليوم
    soil_moisture_pct: float  # نسبة الماء المتاح المتبقّي = (TAW − Dr)/TAW ×100
    ks: float  # معامل الإجهاد المائيّ المُطبَّق هذا اليوم (1 = بلا إجهاد)
    eta_mm: float  # ET الفعليّ = Ks·ETc (مُخفَّض تحت الإجهاد)
    stressed: bool  # هل تجاوز النضوب RAW (بدأ الإجهاد)؟

    def to_dict(self) -> dict:
        return {
            "day": self.day,
            "depletion_mm": round(self.depletion_mm, 2),
            "soil_moisture_pct": round(self.soil_moisture_pct, 1),
            "ks": round(self.ks, 3),
            "eta_mm": round(self.eta_mm, 2),
            "stressed": self.stressed,
        }


@dataclass
class TrajectorySummary:
    """مُلخّص مسار كامل (يُحسَب من DayStates)."""

    days: int
    total_irrigation_mm: float
    total_eta_mm: float
    stress_days: int
    max_depletion_mm: float
    final_depletion_mm: float
    final_soil_moisture_pct: float
    states: list[DayState] = field(default_factory=list)

    def to_dict(self, include_states: bool = True) -> dict:
        d = {
            "days": self.days,
            "total_irrigation_mm": round(self.total_irrigation_mm, 2),
            "total_eta_mm": round(self.total_eta_mm, 2),
            "stress_days": self.stress_days,
            "max_depletion_mm": round(self.max_depletion_mm, 2),
            "final_depletion_mm": round(self.final_depletion_mm, 2),
            "final_soil_moisture_pct": round(self.final_soil_moisture_pct, 1),
        }
        if include_states:
            d["states"] = [s.to_dict() for s in self.states]
        return d


def _ks(depletion_mm: float, taw_mm: float, raw_mm: float) -> float:
    """معامل الإجهاد المائيّ Ks (FAO-56 معادلة 84).

    Ks = 1 طالما النضوب ≤ RAW (ماء متاح بسهولة)؛ وبعده ينحدر خطّيّاً إلى 0 عند TAW
    (الذبول). يُقصَر إلى [0, 1].
    """
    if depletion_mm <= raw_mm:
        return 1.0
    denom = taw_mm - raw_mm
    if denom <= 0:
        return 0.0
    ks = (taw_mm - depletion_mm) / denom
    return max(0.0, min(1.0, ks))


def simulate_trajectory(
    initial_depletion_mm: float,
    taw_mm: float,
    raw_mm: float,
    days: list[DayPlan],
) -> TrajectorySummary:
    """يحاكي نضوب منطقة الجذور يوماً بيوم (FAO-56 ميزان الماء، فصل ٨).

    لكلّ يوم: يُحسَب Ks من نضوب بداية اليوم، ثمّ ET الفعليّ ``ETa = Ks·ETc`` (الإجهاد
    يخفّض الامتصاص)، ثمّ يُحدَّث النضوب ``Dr = Dr_prev + ETa − مطر − ريّ`` ويُقصَر إلى
    ``[0, TAW]`` (الفائض = تسرّب عميق؛ النضوب لا يَسلب). يرفع ``ValueError`` لمدخلات غير صالحة.
    """
    if taw_mm <= 0:
        raise ValueError("TAW يجب أن يكون موجباً (مم).")
    if raw_mm <= 0 or raw_mm > taw_mm:
        raise ValueError("RAW يجب أن يكون في (0, TAW].")
    if initial_depletion_mm < 0 or initial_depletion_mm > taw_mm:
        raise ValueError("النضوب الابتدائيّ يجب أن يكون في [0, TAW].")

    dr = float(initial_depletion_mm)
    states: list[DayState] = []
    total_irrigation = 0.0
    total_eta = 0.0
    stress_days = 0
    max_depletion = dr

    for i, plan in enumerate(days, start=1):
        if plan.etc_mm < 0 or plan.rain_mm < 0 or plan.irrigation_mm < 0:
            raise ValueError(f"اليوم {i}: ETc/مطر/ريّ يجب ألّا تكون سالبة.")
        ks = _ks(dr, taw_mm, raw_mm)
        eta = ks * plan.etc_mm
        dr = dr + eta - plan.rain_mm - plan.irrigation_mm
        # القصّ الفيزيائيّ: النضوب لا يَسلب (الفائض تسرّب عميق) ولا يتجاوز TAW (الذبول التامّ).
        dr = max(0.0, min(dr, taw_mm))
        stressed = dr > raw_mm
        soil_pct = (taw_mm - dr) / taw_mm * 100.0
        states.append(
            DayState(
                day=i,
                depletion_mm=dr,
                soil_moisture_pct=soil_pct,
                ks=ks,
                eta_mm=eta,
                stressed=stressed,
            )
        )
        total_irrigation += plan.irrigation_mm
        total_eta += eta
        stress_days += 1 if stressed else 0
        max_depletion = max(max_depletion, dr)

    final_dr = states[-1].depletion_mm if states else dr
    return TrajectorySummary(
        days=len(states),
        total_irrigation_mm=total_irrigation,
        total_eta_mm=total_eta,
        stress_days=stress_days,
        max_depletion_mm=max_depletion,
        final_depletion_mm=final_dr,
        final_soil_moisture_pct=(taw_mm - final_dr) / taw_mm * 100.0,
        states=states,
    )


# ─── محوّلات «ماذا لو» على جدول الريّ ──────────────────────────────────────────
def delay_irrigation(days: list[DayPlan], delay_days: int) -> list[DayPlan]:
    """يؤجّل كلّ أحداث الريّ ``delay_days`` يوماً (ينقل عمق الريّ لأيّام لاحقة).

    الأيّام المنزاحة خارج الأفق تُفقَد (الريّ لم يحدث ضمن النافذة). ``delay_days`` ≤ 0 ⇒ نسخة كما هي.
    """
    if delay_days <= 0:
        return [DayPlan(d.etc_mm, d.rain_mm, d.irrigation_mm) for d in days]
    n = len(days)
    out = [DayPlan(d.etc_mm, d.rain_mm, 0.0) for d in days]
    for idx, d in enumerate(days):
        if d.irrigation_mm > 0:
            tgt = idx + delay_days
            if tgt < n:
                out[tgt].irrigation_mm += d.irrigation_mm
    return out


def scale_irrigation(days: list[DayPlan], factor: float) -> list[DayPlan]:
    """يضرب عمق الريّ بمعامل (مثل 0.8 لخفض ٢٠٪). ``factor`` < 0 ⇒ ValueError."""
    if factor < 0:
        raise ValueError("معامل الريّ يجب ألّا يكون سالباً.")
    return [DayPlan(d.etc_mm, d.rain_mm, d.irrigation_mm * factor) for d in days]


# ─── المقارنة (أساس مقابل بديل) ────────────────────────────────────────────────
def compare_scenarios(
    taw_mm: float,
    raw_mm: float,
    initial_depletion_mm: float,
    baseline_days: list[DayPlan],
    scenario_days: list[DayPlan],
) -> dict:
    """يقارن مسارَي ريّ (أساس مقابل بديل) ويُرجِع المقارنات + مُلخّصاً صادقاً.

    صدق: المقارنة على **أيّام الإجهاد ونضوب الجذور واستهلاك الماء** فقط — لا غلّة مُلفّقة.
    """
    base = simulate_trajectory(initial_depletion_mm, taw_mm, raw_mm, baseline_days)
    scen = simulate_trajectory(initial_depletion_mm, taw_mm, raw_mm, scenario_days)

    def cmp(metric_ar: str, b: float, s: float, unit: str) -> dict:
        return {
            "metric_ar": metric_ar,
            "baseline": round(b, 2),
            "scenario": round(s, 2),
            "delta": round(s - b, 2),
            "unit": unit,
        }

    comparisons = [
        cmp("إجماليّ الريّ", base.total_irrigation_mm, scen.total_irrigation_mm, "مم"),
        cmp("أيّام الإجهاد", base.stress_days, scen.stress_days, "يوم"),
        cmp("أقصى نضوب", base.max_depletion_mm, scen.max_depletion_mm, "مم"),
        cmp("ET الفعليّ الكلّيّ", base.total_eta_mm, scen.total_eta_mm, "مم"),
        cmp(
            "رطوبة التربة الختاميّة",
            base.final_soil_moisture_pct,
            scen.final_soil_moisture_pct,
            "٪",
        ),
    ]
    water_saved = base.total_irrigation_mm - scen.total_irrigation_mm
    extra_stress = scen.stress_days - base.stress_days
    summary = (
        f"البديل {'يوفّر' if water_saved > 0 else 'يزيد'} {abs(water_saved):.1f} مم ريّ "
        f"مقابل {'+' if extra_stress >= 0 else ''}{extra_stress} يوم إجهاد. "
        "حساب فيزيائيّ (FAO-56) للاستبصار — القرار للمزارع، ولا يُقدَّر أثر الغلّة (غير مُنمذَج)."
    )
    return {
        "scenario_type": "water_twin_trajectory",
        "baseline": base.to_dict(),
        "scenario": scen.to_dict(),
        "comparisons": comparisons,
        "summary_ar": summary,
    }
