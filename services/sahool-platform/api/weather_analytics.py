"""
api/weather_analytics.py — تحليل سجلّ الطقس اليومي إلى ذكاء زراعي

جانب جديد: يحوّل سجلّ طقس خام (يومي) إلى مؤشّرات قرار:
  • مؤشّر الإجهاد الحراري (Heat Stress Index) + عدّ أيّام الخطر
  • ET0 من **منتج سلسلة محرّك الطقس** (WS-C.1b Zero-Legacy — لا نواة محلّيّة؛ المحرّك
    مالك الفلك date→DOY→Ra→ET0). تعذّر المحرّك ⇒ تدهور جزئيّ صريح (لا اختلاق).
  • العجز المائي (ET0 − مطر) — يحدّد الاحتياج الريّي
  • تصنيف المخاطر اليومي (حرّ/رياح/ملائم)
  • ملخّص موسمي للقرار الزراعي

تَحقّق ميداني: عُوير على سجلّ الحزم (365 يوماً) + بيانات الجوف 5 سنوات
(2021-2025، NASA POWER + Open-Meteo). النتائج: أمطار ~80 مم/سنة، عجز مائي
~1900 مم/سنة (ريّ ضروري كلّيّاً)، نافذة إجهاد حراري ~120 يوماً (ماي-سبت).

⚠ يعمل على بيانات يُدخلها المستخدم (سجلّ محطّته/مصدره). الجودة تتبع جودة
المُدخل. ET0 يُنفَّذ في المحرّك المرجعيّ لا هنا. لا يستبدل نشرات الأرصاد الرسميّة للتنبّؤ.
"""

from __future__ import annotations

import logging

from core.thresholds import (
    CLIMATE_HOT_DAY_TMAX_C,
    CLIMATE_SEVERE_HEAT_TMAX_C,
    FROST_RISK_C,
)

# WS-C.1b Zero-Legacy: لا نواة ET0 محلّيّة. ET0 يُجلَب من **منتج سلسلة محرّك الطقس**
# (get_et0_series) — المحرّك مصدر ET0 الوحيد ومالك الفلك (date→DOY→Ra→ET0).
from api.weather_service_client import get_et0_series

_log = logging.getLogger("weather_analytics")


# عتبات إحصاء المناخ (°م) — من المصدر الموحّد core.thresholds (نفس القيم).
_HEAT_STRESS_C = CLIMATE_HOT_DAY_TMAX_C  # «يوم حارّ» في الإحصاء المناخيّ
_SEVERE_HEAT_C = CLIMATE_SEVERE_HEAT_TMAX_C  # «حرّ شديد»
_FROST_C = FROST_RISK_C  # تحتها خطر صقيع
_HIGH_WIND_KMH = 30  # فوقها إجهاد رياح/تعرية

# خطّ عرض افتراضيّ للإحصاء المناخيّ حين لا يُمرَّر (اليمن الداخليّ ~16°N) — يُمرَّر للمحرّك
# ليحسب Ra؛ ليس نواة ET0 (المحرّك يملك الحساب). المُوجِّه يقبل lat صريحاً كتجاوز.
_DEFAULT_LAT_DEG = 16.0

# منتجات التحليل المستقلّة عن ET0 (تبقى صحيحة عند تعذّر المحرّك).
_ET0_INDEPENDENT_PRODUCTS = ["heat", "frost", "wind", "rain"]
# منتجات تعتمد على ET0 (تُوسَم unavailable عند تعذّر المحرّك، بلا اختلاق).
_ET0_DEPENDENT_PRODUCTS = ["et0", "annual_water_deficit", "irrigation_dependence"]


def heat_stress_index(temp_max_c: float) -> dict:
    """تصنيف الإجهاد الحراري ليوم واحد من العظمى."""
    if temp_max_c >= _SEVERE_HEAT_C:
        level, ar = "severe", "شديد — خطر فشل عقد الثمار والإزهار"
    elif temp_max_c >= _HEAT_STRESS_C:
        level, ar = "high", "مرتفع — إجهاد على معظم المحاصيل"
    elif temp_max_c >= 32:
        level, ar = "moderate", "متوسّط — راقب المحاصيل الحسّاسة"
    else:
        level, ar = "low", "منخفض — مريح للنموّ"
    return {"temp_max_c": temp_max_c, "level": level, "level_ar": ar}


def _irrigation_dependency_ar(annual_water_deficit_mm: float) -> str:
    if annual_water_deficit_mm > 500:
        return "ريّ ضروري بالكامل — العجز المائي ضخم (الأمطار لا تغطّي التبخّر)."
    if annual_water_deficit_mm > 0:
        return "ريّ تكميلي — الأمطار تغطّي جزءاً من الاحتياج."
    return "بعليّ ممكن — الأمطار تكفي أو تفوق التبخّر."


async def analyze_weather_log(records: list[dict], lat: float = _DEFAULT_LAT_DEG) -> dict:
    """يحلّل سجلّ طقس يومي إلى مؤشّرات قرار زراعي.

    كلّ record: {date, temp_max_c, temp_min_c, [precipitation_mm], [wind_speed_kmh]}.
    ET0 من **منتج سلسلة محرّك الطقس** (المحرّك مالك الفلك date→DOY→Ra→ET0؛ لا نواة محلّيّة).
    ``lat`` خطّ عرض السجلّ (افتراض اليمن الداخليّ ~16°N) يُمرَّر للمحرّك لحساب Ra. التواريخ
    الفعليّة لكلّ يوم تُمرَّر للمحرّك فيحسب DOY بلا انجراف في السجلّات المتفرّقة/متعدّدة السنوات.

    **fail-closed تدريجيّ (قرار المستخدم):** تعذّر المحرّك ⇒ التحليل المستقلّ عن ET0
    (حرارة/صقيع/رياح/مطر) يبقى صحيحاً كاملاً، وحقول ET0 تُوسَم ``null`` مع
    ``analysis_status="partial"`` + ``availability`` + ``unavailable_products`` — لا اختلاق.
    """
    if not records:
        return {"supported": False, "message_ar": "سجلّ فارغ — أدخل بيانات يوميّة."}

    n = len(records)
    heat_days = severe_days = frost_days = wind_days = 0
    total_rain = 0.0
    daily_t_min: list[float] = []
    daily_t_max: list[float] = []
    daily_dates: list[str | None] = []

    for r in records:
        try:
            tmax = float(r["temp_max_c"])
            tmin = float(r["temp_min_c"])
        except (KeyError, ValueError, TypeError):
            continue
        # الإجهاد الحراري
        if tmax >= _SEVERE_HEAT_C:
            severe_days += 1
            heat_days += 1
        elif tmax >= _HEAT_STRESS_C:
            heat_days += 1
        if tmin <= _FROST_C:
            frost_days += 1
        # الرياح
        w = r.get("wind_speed_kmh")
        if w is not None:
            try:
                if float(w) >= _HIGH_WIND_KMH:
                    wind_days += 1
            except (ValueError, TypeError):
                _log.debug("تخطّي قيمة رياح غير رقميّة: %r", w)
        # المطر
        p = r.get("precipitation_mm")
        if p is not None:
            try:
                total_rain += float(p)
            except (ValueError, TypeError):
                _log.debug("تخطّي قيمة مطر غير رقميّة: %r", p)
        # سلسلة ET0 (تُحسب في المحرّك): نجمع الحرارة + التاريخ الفعليّ لكلّ يوم صالح.
        daily_t_min.append(tmin)
        daily_t_max.append(tmax)
        _d = str(r.get("date", "") or "")
        daily_dates.append(_d if len(_d) >= 10 else None)

    years = max(n / 365.0, 0.01)

    base = {
        "supported": True,
        "days_analyzed": n,
        "heat_stress_days": heat_days,
        "severe_heat_days": severe_days,
        "frost_days": frost_days,
        "high_wind_days": wind_days,
        "total_rainfall_mm": round(total_rain, 1),
        "annual_rainfall_mm": round(total_rain / years, 1),
        "heat_window_ar": (
            f"~{heat_days} يوم إجهاد حراري ({round(heat_days / years)} يوم/سنة) — "
            "تجنّب المراحل الحسّاسة (إزهار/عقد) في هذه النافذة."
        ),
        "verdict_ar": (
            "مناخ صحراوي: ريّ دقيق + محاصيل متحمّلة للحرّ + تجنّب الإزهار صيفاً "
            "+ مصدّات رياح ربيعاً. راجع التصنيف الاستراتيجي للمحاصيل الفاخرة."
            if heat_days / years > 60
            else "مناخ معتدل نسبيّاً — مرونة أوسع في اختيار المحاصيل والمواعيد."
        ),
        "disclaimer_ar": (
            "تحليل لبيانات أُدخلت؛ الجودة تتبع المصدر. لا يستبدل نشرات الأرصاد "
            "الرسميّة. عايِر بمحطّتك المحلّيّة إن أمكن."
        ),
    }

    # ET0 من منتج سلسلة محرّك الطقس (بتواريخ فعليّة). تعذّره ⇒ تدهور جزئيّ صريح (لا اختلاق).
    try:
        et0_series = await get_et0_series(
            daily_t_min=daily_t_min,
            daily_t_max=daily_t_max,
            lat_deg=lat,
            daily_dates=daily_dates,
        )
    except Exception as exc:  # noqa: BLE001 — تعذّر المحرّك ⇒ تدهور جزئيّ (fail-closed، لا محلّيّ)
        _log.warning("weather-engine ET0 series unavailable — partial analysis: %s", exc)
        return {
            **base,
            "analysis_status": "partial",
            "availability": {**{p: True for p in _ET0_INDEPENDENT_PRODUCTS}, "et0": False},
            "computed_products": list(_ET0_INDEPENDENT_PRODUCTS),
            "unavailable_products": list(_ET0_DEPENDENT_PRODUCTS),
            "computed_et0_total_mm": None,
            "annual_et0_mm": None,
            "annual_water_deficit_mm": None,
            "irrigation_dependency_ar": None,
            "limitations": [
                "Canonical ET0 product unavailable — heat/frost/wind/rain analysis unaffected."
            ],
            "note_ar": (
                "تعذّر منتج ET0 المرجعيّ (محرّك الطقس)؛ التحليل الحراري/المطريّ مكتمل "
                "والتحليل المائيّ مؤجَّل (لا حساب ET0 محلّيّ)."
            ),
        }

    daily_et0 = et0_series.get("daily_et0_mm") or []
    total_et0 = sum(float(v) for v in daily_et0 if v is not None)
    annual_water_deficit = (total_et0 - total_rain) / years

    return {
        **base,
        "analysis_status": "complete",
        "availability": {**{p: True for p in _ET0_INDEPENDENT_PRODUCTS}, "et0": True},
        "computed_products": [*_ET0_INDEPENDENT_PRODUCTS, "et0"],
        "unavailable_products": [],
        "computed_et0_total_mm": round(total_et0, 1),
        "annual_et0_mm": round(total_et0 / years, 1),
        "annual_water_deficit_mm": round(annual_water_deficit, 1),
        "irrigation_dependency_ar": _irrigation_dependency_ar(annual_water_deficit),
        "et0_method": "weather-engine",
        "note_ar": (
            "ET0 من منتج محرّك الطقس المرجعيّ (FAO-56؛ المحرّك مالك الحساب الفلكيّ). "
            "العجز المائي = ET0 − المطر يحدّد الاحتياج الريّي الفعلي."
        ),
    }


def seasonal_planting_guide(records: list[dict]) -> dict:
    """دليل المواسم من السجلّ: متى الزراعة الأمثل ومتى الإجهاد (شهريّاً)."""
    if not records:
        return {"supported": False, "message_ar": "سجلّ فارغ."}
    from collections import defaultdict

    mon_tmax = defaultdict(list)
    for r in records:
        d = str(r.get("date", ""))
        if len(d) >= 7 and d[5:7].isdigit():
            try:
                mon_tmax[int(d[5:7])].append(float(r["temp_max_c"]))
            except (KeyError, ValueError, TypeError):
                _log.debug("تخطّي سجلّ حرارة ناقص/تالف: %r", d)
    names = {
        1: "يناير",
        2: "فبراير",
        3: "مارس",
        4: "أبريل",
        5: "مايو",
        6: "يونيو",
        7: "يوليو",
        8: "أغسطس",
        9: "سبتمبر",
        10: "أكتوبر",
        11: "نوفمبر",
        12: "ديسمبر",
    }
    months = []
    for m in sorted(mon_tmax):
        avg = sum(mon_tmax[m]) / len(mon_tmax[m])
        if avg >= _HEAT_STRESS_C:
            window, w_ar = "heat_stress", "إجهاد حراري — محاصيل متحمّلة فقط"
        elif avg <= 30:
            window, w_ar = "optimal", "أمثل — حبوب وخضروات"
        else:
            window, w_ar = "transition", "انتقالي — راقب الحرارة/الرياح"
        months.append(
            {
                "month": m,
                "month_ar": names[m],
                "avg_tmax_c": round(avg, 1),
                "window": window,
                "window_ar": w_ar,
            }
        )
    optimal = [m["month_ar"] for m in months if m["window"] == "optimal"]
    heat = [m["month_ar"] for m in months if m["window"] == "heat_stress"]
    return {
        "supported": True,
        "months": months,
        "optimal_season_ar": optimal,
        "heat_stress_season_ar": heat,
        "summary_ar": (
            f"الموسم الأمثل: {'، '.join(optimal) if optimal else 'محدود'}. "
            f"نافذة الإجهاد الحراري: {'، '.join(heat) if heat else 'لا يُذكر'}. "
            "ازرع الحبوب والخضروات في الموسم البارد، واحفظ الصيف للمتحمّلات."
        ),
        "disclaimer_ar": "دليل من بيانات السجلّ — كيّفه حسب المحصول والصنف المحدّد.",
    }
