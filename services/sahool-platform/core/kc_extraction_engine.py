"""core/kc_extraction_engine.py — اشتقاق معامل المحصول Kc المكافئ (FAO-56) من مخرجات
WOFOST/PCSE (نقيّ، حتميّ، بلا تبعيّة pcse/numpy).

PCSE/WOFOST **لا يُخرِج Kc**؛ يُخرِج مكوّنات فيزيائيّة يوميّة: النتح الفعليّ TRA والتبخّر
الفعليّ EVS، ونظيريهما الكامنين TRAMX/EVSMX (بلا إجهاد مائيّ). بالطريقة البَعديّة
(post-hoc) نشتقّ سلسلة Kc مكافئة تُقابِل إطار FAO-56، فنستبدل قيم FAO العامّة بمعامل
**محلّيّ ديناميكيّ** للصنف/الحقل/الموسم (يُغذّي season_simulation بدل kc_map الثابت):

    Kc_act  = (TRA + EVS) / ET0          ← الفعليّ (موسم حقيقيّ بمطر/ريّ/إجهاد)
    Kc_pot  = (TRAMX + EVSMX) / ET0      ← المعيار (سيناريو ريّ كامل بلا إجهاد) = Kc «القياسيّ»
    Kcb     = TRA / ET0                  ← الأساسيّ (نتح فقط)؛ Kcb_pot = TRAMX / ET0
    Ke      = EVS / ET0                  ← تبخّر التربة
    Ks      = TRA / TRAMX                ← معامل الإجهاد المائيّ ∈ [0,1]

مزالق حرجة (مُعالَجة هنا، كانت أخطاءً في الشيفرة المرجعيّة):
  • **الوحدات:** مخرجات WOFOST بـcm/يوم ⇒ تُضرَب في 10 لتصير mm/يوم لتطابق ET0. ويجب
    تطبيق التحويل على **المتغيّر الصحيح** لكلٍّ (EVS→EVS لا TR، TRAMX→TRAMX لا TR).
  • **ET0:** يجب أن يُحسَب مستقلّاً بمعادلة FAO-56 Penman-Monteith على نفس بيانات
    الطقس — لا ET0 الداخليّ لـPCSE (Penman 1963 + CFET ⇒ انحراف منهجيّ). تُمرَّر ET0
    هنا جاهزةً (mm/يوم) من حاسب FAO-56.
  • **CFET:** WOFOST يضرب النتح الكامن في معامل CFET (1.0 لأغلب المحاصيل، ~1.15 لبعضها).
    للمطابقة الصارمة مع FAO يُقسَم TRAMX على CFET قبل الاشتقاق.
  • **فصل الإجهاد:** Kc «القياسيّ» يُستخرَج من سيناريو ريّ كامل فقط؛ لا تخلطه بموسم مُجهَد.
"""

from __future__ import annotations

from dataclasses import dataclass

_CM_TO_MM = 10.0  # مخرجات WOFOST cm/يوم → mm/يوم

# حدود مراحل النموّ بدلالة DVS (0=إنبات، 1=إزهار، 2=نضج) — مطابِقة لإطار FAO-56.
_DVS_INI_MAX = 0.2  # الابتدائيّة: قبل النموّ السريع (تبخّر التربة مسيطِر)
_DVS_MID_MIN, _DVS_MID_MAX = 1.0, 1.3  # المنتصف (الذروة): الإزهار→بدء الامتلاء
_DVS_END_MIN = 1.6  # المتأخّرة: نحو النضج (شيخوخة الأوراق)


@dataclass(frozen=True)
class DailyFlux:
    """مكوّنات يوميّة من WOFOST (النتح/التبخّر بـcm/يوم) + ET0 بـmm/يوم + LAI/DVS."""

    tra_cm: float  # النتح الفعليّ
    evs_cm: float  # تبخّر التربة الفعليّ
    tramx_cm: float  # النتح الكامن (بلا إجهاد)
    evsmx_cm: float  # تبخّر التربة الكامن
    et0_mm: float  # ET0 المرجعيّ (FAO-56 PM، mm/يوم) — لا ET0 الداخليّ لـPCSE
    lai: float = 0.0
    dvs: float = 0.0


@dataclass(frozen=True)
class DailyKc:
    """معاملات Kc اليوميّة المشتقّة (None حين ET0=0 — لا قسمة على صفر)."""

    kc_act: float | None  # الفعليّ (TRA+EVS)/ET0
    kc_pot: float | None  # القياسيّ/الكامن (TRAMX+EVSMX)/ET0
    kcb_act: float | None  # الأساسيّ الفعليّ TRA/ET0
    kcb_pot: float | None  # الأساسيّ الكامن TRAMX/ET0
    ke: float | None  # تبخّر التربة EVS/ET0
    ks: float | None  # الإجهاد المائيّ TRA/TRAMX ∈ [0,1]


@dataclass(frozen=True)
class FaoStageKc:
    """معاملات FAO-56 الثلاثيّة المُلائَمة (قابلة لإحلال kc_map الثابت)."""

    kc_ini: float | None
    kc_mid: float | None
    kc_end: float | None
    kcb_ini: float | None
    kcb_mid: float | None
    kcb_end: float | None


def _ratio(numer_mm: float, denom_mm: float) -> float | None:
    """نسبة آمنة: denom=0 ⇒ None (لا قسمة على صفر)."""
    if denom_mm is None or denom_mm == 0:
        return None
    return numer_mm / denom_mm


def derive_daily_kc(flux: DailyFlux, *, cfet: float = 1.0) -> DailyKc:
    """يشتقّ Kc اليوميّة من مكوّنات يوم واحد (نقيّ). يطبّق تحويل الوحدات على المتغيّر
    الصحيح لكلٍّ، وقسمة CFET على النتح الكامن للمطابقة الصارمة مع FAO."""
    cf = cfet if cfet and cfet > 0 else 1.0
    tra = flux.tra_cm * _CM_TO_MM
    evs = flux.evs_cm * _CM_TO_MM
    tramx = (flux.tramx_cm / cf) * _CM_TO_MM
    evsmx = flux.evsmx_cm * _CM_TO_MM
    et0 = flux.et0_mm
    # Ks نسبة نتح/نتح (الوحدات تُختصَر) — يُحسَب من القيم الأصليّة (cm) مع CFET.
    ks = _ratio(flux.tra_cm, flux.tramx_cm / cf)
    return DailyKc(
        kc_act=_ratio(tra + evs, et0),
        kc_pot=_ratio(tramx + evsmx, et0),
        kcb_act=_ratio(tra, et0),
        kcb_pot=_ratio(tramx, et0),
        ke=_ratio(evs, et0),
        ks=None if ks is None else max(0.0, min(1.0, ks)),
    )


def derive_series(fluxes: list[DailyFlux], *, cfet: float = 1.0) -> list[DailyKc]:
    """يشتقّ سلسلة Kc يوميّة لموسم كامل (نقيّ)."""
    return [derive_daily_kc(f, cfet=cfet) for f in fluxes]


def _moving_average(values: list[float | None], window: int) -> list[float | None]:
    """متوسّط متحرّك مركزيّ يتجاهل None — لتنعيم تذبذب Kc الابتدائيّ (قفزات التبخّر)."""
    n = len(values)
    half = max(1, window) // 2
    out: list[float | None] = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        win = [v for v in values[lo:hi] if v is not None]
        out.append(sum(win) / len(win) if win else None)
    return out


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def fit_fao_stages(
    fluxes: list[DailyFlux], kcs: list[DailyKc], *, smooth_window: int = 7
) -> FaoStageKc:
    """يُلائم معاملات FAO الثلاثيّة (ابتدائيّ/منتصف/متأخّر) بتقسيم DVS — من Kc **القياسيّ**
    (kc_pot؛ يجب أن يكون المدخل سيناريو ريّ كامل). الابتدائيّ يُنعَّم بمتوسّط متحرّك (تذبذب
    التبخّر)، والمتأخّر = متوسّط آخر 10 أيّام من مرحلة النضج (مطابقةً لـFAO-56)."""
    if len(fluxes) != len(kcs):
        raise ValueError("عدد المكوّنات لا يطابق عدد قيم Kc")

    kc_pot = [k.kc_pot for k in kcs]
    kcb_pot = [k.kcb_pot for k in kcs]
    kc_pot_smooth = _moving_average(kc_pot, smooth_window)

    ini, mid, end_idx = [], [], []
    for i, f in enumerate(fluxes):
        if f.dvs < _DVS_INI_MAX:
            ini.append(i)
        elif _DVS_MID_MIN <= f.dvs < _DVS_MID_MAX:
            mid.append(i)
        elif f.dvs >= _DVS_END_MIN:
            end_idx.append(i)

    def _end_tail(series):  # آخر 10 أيّام من مرحلة النضج
        tail = [series[i] for i in end_idx][-10:]
        return _mean(tail)

    return FaoStageKc(
        kc_ini=_mean([kc_pot_smooth[i] for i in ini]),
        kc_mid=_mean([kc_pot[i] for i in mid]),
        kc_end=_end_tail(kc_pot),
        kcb_ini=_mean([kcb_pot[i] for i in ini]),
        kcb_mid=_mean([kcb_pot[i] for i in mid]),
        kcb_end=_end_tail(kcb_pot),
    )
