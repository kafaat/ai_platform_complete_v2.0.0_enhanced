"""
api/seasonal_risk.py — نوافذ المخاطر المناخيّة الموسميّة + ساعات البرودة

جانب جديد (فجوة حقيقيّة): الملاءمة لا تكفي — قد تكون التربة والمحصول مناسبين
نظريّاً، لكن **تزامن مرحلة حسّاسة مع خطر مناخي** يُفشل الموسم:
  • موجة حرّ أثناء الإزهار → فشل عقد الثمار
  • صقيع مبكر/متأخّر → تلف
  • مطر أثناء الحصاد → تعفّن/تدنّي جودة
  • رطوبة عالية في مرحلة حسّاسة → أمراض فطريّة

كما يضيف **حاسبة ساعات البرودة** (chill hours) — الأشجار المتساقطة (تفاح/خوخ)
تحتاج حدّاً أدنى من ساعات البرودة الشتويّة لتزهر؛ السهول الحارّة لا توفّرها.

المصدر: مبادئ علم المناخ الزراعي (phenology × climate hazards) + بيانات
الأقاليم اليمنيّة الموثّقة. توجّه تحذيري لا يفرض.

⚠ تقدير إرشادي مبني على أنماط الإقليم العامّة، لا تنبّؤ جوّي يومي. للدقّة:
تكامل مع بيانات أرصاد لحظيّة في النشر. لا يستبدل متابعة المزارع ونشرات الطقس.
"""

from __future__ import annotations

from api.agro_climate_zones import _ZONES

# ─── المخاطر المناخيّة حسب الإقليم (متى تنشط) ────────────────────
# مبنيّ على مناخ كلّ إقليم الموثّق (حرارة/مطر/رطوبة/صقيع)
_ZONE_HAZARDS: dict[str, list[dict]] = {
    "tihama": [
        {
            "hazard_ar": "موجات حرّ شديدة",
            "season_ar": "الصيف (يونيو-سبتمبر)",
            "risk_to_ar": "الإزهار وعقد الثمار",
            "severity": "high",
        },
        {
            "hazard_ar": "رطوبة بحريّة عالية",
            "season_ar": "على مدار السنة",
            "risk_to_ar": "أمراض فطريّة",
            "severity": "medium",
        },
        {
            "hazard_ar": "سيول مفاجئة",
            "season_ar": "موسم الأمطار (يوليو-أغسطس)",
            "risk_to_ar": "انجراف/إغراق",
            "severity": "medium",
        },
    ],
    "western_highlands": [
        {
            "hazard_ar": "أمطار غزيرة وقت الحصاد",
            "season_ar": "الصيف الممطر",
            "risk_to_ar": "تعفّن الحبوب/تدنّي الجودة",
            "severity": "medium",
        },
        {
            "hazard_ar": "ضباب ورطوبة",
            "season_ar": "موسم الأمطار",
            "risk_to_ar": "أمراض فطريّة (خاصّةً البنّ/الخضار)",
            "severity": "medium",
        },
        {
            "hazard_ar": "صقيع خفيف",
            "season_ar": "ليالي الشتاء (القمم العالية)",
            "risk_to_ar": "البراعم الزهريّة",
            "severity": "low",
        },
    ],
    "central_highlands": [
        {
            "hazard_ar": "صقيع شتوي",
            "season_ar": "ليالي الشتاء (ديسمبر-فبراير)",
            "risk_to_ar": "المحاصيل الحسّاسة والبراعم",
            "severity": "high",
        },
        {
            "hazard_ar": "بَرَد",
            "season_ar": "العواصف الرعديّة الربيعيّة/الصيفيّة",
            "risk_to_ar": "تلف ميكانيكي للثمار والأوراق",
            "severity": "medium",
        },
        {
            "hazard_ar": "تذبذب المطر",
            "season_ar": "الصيف",
            "risk_to_ar": "إجهاد مائي للبعليّ",
            "severity": "medium",
        },
    ],
    "eastern_plateau": [
        {
            "hazard_ar": "حرارة شديدة + جفاف",
            "season_ar": "الصيف",
            "risk_to_ar": "الإجهاد الحراري والمائي",
            "severity": "high",
        },
        {
            "hazard_ar": "سيول الأودية المفاجئة",
            "season_ar": "الأمطار النادرة",
            "risk_to_ar": "جرف المحاصيل",
            "severity": "medium",
        },
    ],
    "inland_desert": [
        {
            "hazard_ar": "موجات حرّ مدمّرة (>42°م)",
            "season_ar": "الصيف",
            "risk_to_ar": "الإزهار وكلّ المراحل الحسّاسة",
            "severity": "high",
        },
        {
            "hazard_ar": "جفاف ممتدّ",
            "season_ar": "معظم العام",
            "risk_to_ar": "نقص الماء (اعتماد كلّي على الجوفي)",
            "severity": "high",
        },
        {
            "hazard_ar": "عواصف ترابيّة/رياح",
            "season_ar": "الربيع/الصيف",
            "risk_to_ar": "إجهاد ميكانيكي وتعرية",
            "severity": "medium",
        },
    ],
    "southern_coast": [
        {
            "hazard_ar": "حرارة ورطوبة عالية",
            "season_ar": "الصيف",
            "risk_to_ar": "الإجهاد والأمراض الفطريّة",
            "severity": "high",
        },
        {
            "hazard_ar": "رياح موسميّة (المهرة)",
            "season_ar": "الخريف (موسم ظفار)",
            "risk_to_ar": "إجهاد ميكانيكي",
            "severity": "medium",
        },
    ],
}

# المراحل الحسّاسة العامّة لكلّ خطر (للربط بالتقويم)
_STAGE_SENSITIVITY = {
    "الإزهار": ["موجات حرّ", "صقيع", "رياح", "بَرَد"],
    "عقد الثمار": ["موجات حرّ", "رياح"],
    "الحصاد": ["أمطار", "رطوبة"],
    "النموّ الخضري": ["جفاف", "إجهاد مائي"],
}


def zone_risk_calendar(zone: str) -> dict:
    """نوافذ المخاطر المناخيّة الموسميّة لإقليم محدّد."""
    z = _ZONES.get(zone.strip().lower())
    hazards = _ZONE_HAZARDS.get(zone.strip().lower())
    if not z or hazards is None:
        return {
            "supported": False,
            "message_ar": f"لا بيانات مخاطر لإقليم «{zone}». المتاح: "
            + "، ".join(_ZONES[k]["name_ar"] for k in _ZONE_HAZARDS),
        }
    high = [h for h in hazards if h["severity"] == "high"]
    return {
        "supported": True,
        "zone": zone,
        "zone_name_ar": z["name_ar"],
        "hazards": hazards,
        "high_severity_count": len(high),
        "principle_ar": (
            "الملاءمة لا تكفي — تزامن مرحلة حسّاسة (إزهار/حصاد) مع خطر مناخي "
            "(موجة حرّ/صقيع/مطر) قد يُفشل الموسم رغم التربة المناسبة."
        ),
        "advice_ar": (
            "خطّط مواعيد الزراعة بحيث تتجنّب المراحل الحسّاسة نوافذَ الخطر. "
            "راجع تقويم الزراعة + تتبّع GDD لضبط التوقيت."
        ),
        "disclaimer_ar": (
            "تقدير إرشادي من أنماط الإقليم العامّة، لا تنبّؤ جوّي يومي. "
            "تابع نشرات الطقس المحلّيّة في المراحل الحرجة."
        ),
        "source_ar": (
            "مبادئ علم المناخ الزراعي (phenology × climate hazards) + بيانات "
            "الأقاليم اليمنيّة الموثّقة (الأرصاد + الجغرافيا)."
        ),
    }


def stage_risk_check(zone: str, stage_ar: str) -> dict:
    """يفحص مخاطر مرحلة نموّ محدّدة في إقليم (مثلاً الإزهار في الجوف)."""
    cal = zone_risk_calendar(zone)
    if not cal.get("supported"):
        return cal
    # المخاطر التي تهدّد هذه المرحلة
    keywords = []
    for st, hz in _STAGE_SENSITIVITY.items():
        if st in stage_ar or stage_ar in st:
            keywords = hz
            break
    relevant = []
    for h in cal["hazards"]:
        if (
            any(k in h["hazard_ar"] or k in h["risk_to_ar"] for k in keywords)
            or stage_ar in h["risk_to_ar"]
        ):
            relevant.append(h)
    return {
        "supported": True,
        "zone_name_ar": cal["zone_name_ar"],
        "stage_ar": stage_ar,
        "relevant_hazards": relevant,
        "risk_level_ar": (
            "مرتفع — تجنّب هذه المرحلة في نافذة الخطر"
            if any(h["severity"] == "high" for h in relevant)
            else "متوسّط — راقب الطقس"
            if relevant
            else "منخفض — لا مخاطر بارزة معروفة لهذه المرحلة"
        ),
        "advice_ar": (
            "اضبط موعد الزراعة بحيث تقع هذه المرحلة خارج نافذة الخطر (راجع تقويم الزراعة)."
            if relevant
            else "لا تعديل خاصّ مطلوب لهذه المرحلة."
        ),
        "disclaimer_ar": cal["disclaimer_ar"],
    }


# ─── حاسبة ساعات البرودة (chill hours) ──────────────────────────
# قاعدة بسيطة: ساعات البرودة ≈ الساعات السنويّة تحت 7.2°م (45°ف)
# تُقدّر تقريبيّاً من عدد أشهر الشتاء الباردة ومتوسّط حرارتها الدنيا.


def chill_hours_estimate(zone: str) -> dict:
    """يقدّر ساعات البرودة المتاحة في إقليم ويقارنها باحتياج الأشجار المتساقطة."""
    z = _ZONES.get(zone.strip().lower())
    if not z:
        return {"supported": False, "message_ar": f"لا إقليم «{zone}»."}
    tmin = z["temp_c"][0]  # أدنى متوسّط حرارة
    alt_max = z["altitude_m"][1]  # أعلى ارتفاع في الإقليم

    # تقدير ساعات البرودة: الارتفاع والحرارة الدنيا معاً (الليالي الباردة تتراكم)
    # المرتفعات الوسطى الباردة (≤5°م) > الغربيّة المعتدلة عالية الارتفاع > الهضاب
    if tmin <= 5:
        chill = 700  # مرتفعات وسطى باردة (صقيع شتوي)
    elif tmin <= 12 and alt_max >= 2000:
        chill = 450  # مرتفعات غربيّة عالية (ليالٍ باردة، تباين نهاري)
    elif tmin <= 12:
        chill = 250  # مرتفعات معتدلة أقلّ ارتفاعاً
    elif tmin <= 18 and alt_max >= 1000:
        chill = 100  # هضاب/مناطق انتقاليّة (تباين نهاري كبير كالحزم)
    else:
        chill = 0  # سهول حارّة — لا برودة كافية

    # احتياجات أمثلة (ساعات برودة دنيا للإزهار)
    crops_chill = {
        "التفاح": 800,
        "الكمّثرى": 600,
        "اللوز": 300,
        "الخوخ": 400,
        "العنب": 100,
        "الرمّان": 100,
        "التين": 100,
    }
    can_grow = {c: (chill >= need) for c, need in crops_chill.items()}

    return {
        "supported": True,
        "zone": zone,
        "zone_name_ar": z["name_ar"],
        "estimated_chill_hours": chill,
        "min_temp_c": tmin,
        "max_altitude_m": alt_max,
        "crops_chill_requirement": crops_chill,
        "can_satisfy": can_grow,
        "verdict_ar": (
            f"الإقليم يوفّر ~{chill} ساعة برودة. "
            + (
                "كافٍ للأشجار المتساقطة عالية الاحتياج (تفاح/كمّثرى)."
                if chill >= 600
                else "كافٍ للأشجار متوسّطة الاحتياج (خوخ/لوز/رمّان/تين/عنب) لا التفاح التجاري."
                if chill >= 400
                else "محدود — يناسب أشجاراً قليلة الاحتياج (رمّان/تين/عنب) + لوز بحذر."
                if chill >= 100
                else "⚠ لا برودة كافية — الأشجار المتساقطة المحتاجة للبرودة (تفاح) "
                "لن تزهر جيّداً. هذا يفسّر لماذا التفاح للمرتفعات لا السهول."
            )
        ),
        "principle_ar": (
            "ساعات البرودة = الساعات السنويّة تحت ~7°م. الأشجار المتساقطة تحتاج "
            "حدّاً أدنى منها لكسر السكون والإزهار. التباين النهاري الكبير في "
            "المناطق المرتفعة يرفع التراكم رغم نهارها الحارّ."
        ),
        "disclaimer_ar": (
            "تقدير تقريبي من حرارة وارتفاع الإقليم — ساعات البرودة الفعليّة تحتاج "
            "بيانات أرصاد ساعيّة. استعلم عن منطقتك من هيئة البحوث."
        ),
    }
