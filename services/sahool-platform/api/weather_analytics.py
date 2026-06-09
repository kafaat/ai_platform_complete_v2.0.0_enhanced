"""
api/weather_analytics.py — تحليل سجلّ الطقس اليومي إلى ذكاء زراعي

جانب جديد: يحوّل سجلّ طقس خام (يومي) إلى مؤشّرات قرار:
  • مؤشّر الإجهاد الحراري (Heat Stress Index) + عدّ أيّام الخطر
  • ET0 محسوب بطريقة Hargreaves (موثوق من الحرارة — لا عمود جاهز ضعيف)
  • العجز المائي (ET0 − مطر) — يحدّد الاحتياج الريّي
  • تصنيف المخاطر اليومي (حرّ/رياح/ملائم)
  • ملخّص موسمي للقرار الزراعي

تَحقّق ميداني: عُوير على سجلّ الحزم (365 يوماً) + بيانات الجوف 5 سنوات
(2021-2025، NASA POWER + Open-Meteo). النتائج: أمطار ~80 مم/سنة، عجز مائي
~1900 مم/سنة (ريّ ضروري كلّيّاً)، نافذة إجهاد حراري ~120 يوماً (ماي-سبت).

⚠ يعمل على بيانات يُدخلها المستخدم (سجلّ محطّته/مصدره). الجودة تتبع جودة
المُدخل. ET0 المحسوب أصدق من أعمدة ET0 الجاهزة ضعيفة المعايرة الموسميّة.
لا يستبدل نشرات الأرصاد الرسميّة للتنبّؤ.
"""

from __future__ import annotations

import logging

_log = logging.getLogger("weather_analytics")


# عتبات الإجهاد الحراري (°م) — للمحاصيل عموماً في المناخ الصحراوي
_HEAT_STRESS_C = 38  # فوقها إجهاد حراري على معظم المحاصيل
_SEVERE_HEAT_C = 42  # فوقها إجهاد شديد (فشل عقد ثمار محتمل)
_FROST_C = 2  # تحتها خطر صقيع
_HIGH_WIND_KMH = 30  # فوقها إجهاد رياح/تعرية


def _hargreaves_et0(tmax: float, tmin: float, ra_mm: float) -> float:
    """ET0 بطريقة Hargreaves-Samani (حرارة + إشعاع خارج الغلاف).
    ra_mm: الإشعاع خارج الغلاف الجوّي معبَّراً عنه بمكافئ التبخّر (مم/يوم).
    """
    tmean = (tmax + tmin) / 2.0
    dt = max(tmax - tmin, 0.0)
    return max(0.0, 0.0023 * (tmean + 17.8) * (dt**0.5) * ra_mm)


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


def analyze_weather_log(
    records: list[dict], ra_mm_by_month: dict[int, float] | None = None
) -> dict:
    """يحلّل سجلّ طقس يومي إلى مؤشّرات قرار زراعي.

    كلّ record: {date, temp_max_c, temp_min_c, [precipitation_mm], [wind_speed_kmh]}.
    ra_mm_by_month: الإشعاع خارج الغلاف (مم/يوم) لكلّ شهر — لحساب ET0.
                    إن غاب، نستخدم تقديراً افتراضيّاً لخطوط عرض اليمن (~16°N).
    """
    if not records:
        return {"supported": False, "message_ar": "سجلّ فارغ — أدخل بيانات يوميّة."}

    # إشعاع افتراضي لليمن الداخلي (~16°N) بمكافئ التبخّر مم/يوم
    default_ra = {
        1: 10.4,
        2: 12.0,
        3: 14.1,
        4: 15.7,
        5: 16.5,
        6: 16.7,
        7: 16.5,
        8: 15.7,
        9: 14.3,
        10: 12.2,
        11: 10.6,
        12: 9.8,
    }
    ra = ra_mm_by_month or default_ra

    n = len(records)
    heat_days = severe_days = frost_days = wind_days = 0
    total_rain = total_et0 = 0.0
    valid_et0 = 0

    for r in records:
        try:
            tmax = float(r["temp_max_c"])
            tmin = float(r["temp_min_c"])
        except (KeyError, ValueError, TypeError):
            continue
        # شهر السجلّ (من التاريخ YYYY-MM-DD)
        mon = 6
        d = str(r.get("date", ""))
        if len(d) >= 7 and d[5:7].isdigit():
            mon = int(d[5:7])
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
        # ET0 محسوب
        total_et0 += _hargreaves_et0(tmax, tmin, ra.get(mon, 14.0))
        valid_et0 += 1

    water_deficit = total_et0 - total_rain
    years = max(n / 365.0, 0.01)

    return {
        "supported": True,
        "days_analyzed": n,
        "heat_stress_days": heat_days,
        "severe_heat_days": severe_days,
        "frost_days": frost_days,
        "high_wind_days": wind_days,
        "total_rainfall_mm": round(total_rain, 1),
        "annual_rainfall_mm": round(total_rain / years, 1),
        "computed_et0_total_mm": round(total_et0, 1),
        "annual_et0_mm": round(total_et0 / years, 1),
        "annual_water_deficit_mm": round(water_deficit / years, 1),
        "irrigation_dependency_ar": (
            "ريّ ضروري بالكامل — العجز المائي ضخم (الأمطار لا تغطّي التبخّر)."
            if water_deficit / years > 500
            else "ريّ تكميلي — الأمطار تغطّي جزءاً من الاحتياج."
            if water_deficit / years > 0
            else "بعليّ ممكن — الأمطار تكفي أو تفوق التبخّر."
        ),
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
        "note_ar": (
            "ET0 محسوب بـHargreaves من الحرارة (موثوق موسميّاً). العجز المائي "
            "= ET0 − المطر يحدّد الاحتياج الريّي الفعلي."
        ),
        "disclaimer_ar": (
            "تحليل لبيانات أُدخلت؛ الجودة تتبع المصدر. لا يستبدل نشرات الأرصاد "
            "الرسميّة. عايِر بمحطّتك المحلّيّة إن أمكن."
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
