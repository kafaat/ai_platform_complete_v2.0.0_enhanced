"""
api/agro_climate_zones.py — تصنيف الأقاليم المناخيّة-الزراعيّة لليمن

جانب جوهري جديد: الطبقة التي تربط "أين أنت" بـ"ماذا يناسبك". اليمن ليس مناخاً
واحداً بل **6 أقاليم إيكولوجيّة-زراعيّة** متمايزة (تصنيف معتمد علميّاً)، يحدّد
كلٌّ منها ما يُزرع بنجاح طوال العام.

المصدر (موثّق بالبحث):
  • CEFAS (المركز الفرنسي لبحوث الجزيرة العربيّة): 6 أقاليم إيكو-جغرافيّة
    شماليّة كأحزمة شمال-جنوب
  • Wikipedia Geography of Yemen + Britannica + مركز صنعاء للدراسات
  • بيانات الأرصاد اليمنيّة (yemeneco) + هيئة المياه (cso-yemen)

المبدأ: لا توصية محصول بلا معرفة الإقليم. التماثل المناخي يرجّح النجاح، لكن
التربة والصنف والآفات المحلّيّة حاسمة. توجّه لا يفرض.

⚠ الأرقام تقريبيّة (متوسّطات سنويّة)؛ التضاريس المحلّيّة تُحدث تبايناً دقيقاً
(microclimate). استعلم عن منطقتك المحدّدة من هيئة البحوث والإرشاد الزراعي.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, Optional


class AgroZone(str, Enum):
    TIHAMA = "tihama"               # السهل الساحلي الغربي (البحر الأحمر)
    WESTERN_HIGHLANDS = "western_highlands"   # المرتفعات الغربيّة الممطرة
    CENTRAL_HIGHLANDS = "central_highlands"   # المرتفعات الوسطى (الهضبة)
    EASTERN_PLATEAU = "eastern_plateau"       # الهضبة الشرقيّة شبه الصحراويّة
    INLAND_DESERT = "inland_desert"           # الصحراء الداخليّة (الجوف/مأرب/الربع الخالي)
    SOUTHERN_COAST = "southern_coast"         # الساحل الجنوبي (عدن/أبين/حضرموت الساحليّة)


# ─── تعريف الأقاليم الستّة (بيانات موثّقة) ───────────────────────
_ZONES: Dict[str, Dict] = {
    "tihama": {
        "name_ar": "سهل تهامة الساحلي (البحر الأحمر)",
        "governorates_ar": ["الحديدة", "أجزاء من حجة", "أجزاء من تعز الساحليّة"],
        "altitude_m": (0, 200),
        "temp_c": (28, 40),          # حارّ على مدار السنة
        "annual_rain_mm": (50, 130), # شحيح جدّاً (~80 الحديدة)
        "humidity_pct": (50, 70),    # رطوبة بحريّة عالية
        "climate_ar": "استوائي حارّ رطب على مدار السنة، أمطار شحيحة، رطوبة بحريّة عالية",
        "water_source_ar": "ريّ من السيول (الوديان) والمياه الجوفيّة — لا اعتماد على المطر",
        "suited_crops_ar": [
            "النخيل (تمور)", "المانجو", "البابايا", "الموز (بحذر مائي)",
            "السمسم", "الذرة الرفيعة", "القطن", "الخضروات الصيفيّة (بامية/فلفل/باذنجان)",
        ],
        "avoid_ar": ["التفاح/البنّ (يحتاجان برودة)", "محاصيل حسّاسة للحرارة الشديدة"],
        "yemen_note_ar": (
            "أحزمة الوديان الخصبة (زبيد/سردد/مور) مصدر الريّ الأساسي. التبخّر "
            "شديد — الريّ الكفء وحصاد السيول ضروريّان."
        ),
    },
    "western_highlands": {
        "name_ar": "المرتفعات الغربيّة الممطرة",
        "governorates_ar": ["تعز", "إب", "أجزاء من ذمار", "أجزاء من المحويت", "ريمة"],
        "altitude_m": (1500, 3000),
        "temp_c": (12, 28),          # معتدل
        "annual_rain_mm": (760, 1500),  # الأعلى في الجزيرة العربيّة
        "humidity_pct": (40, 70),
        "climate_ar": "معتدل، صيف ممطر (رياح موسميّة)، تباين حراري نهاري كبير، ضباب",
        "water_source_ar": "أمطار موسميّة كافية + مدرّجات تحجز الماء والتربة + سيول",
        "suited_crops_ar": [
            "البنّ (موطنه التاريخي)", "القات", "الحبوب (قمح/شعير/ذرة رفيعة)",
            "التفاح والفواكه المعتدلة (خوخ/كمّثرى)", "العنب", "الخضروات", "البقوليّات",
        ],
        "avoid_ar": ["محاصيل السهول الحارّة البحتة (نخيل التمر التجاري)"],
        "yemen_note_ar": (
            "الإقليم الوحيد بأمطار كافية لزراعة بعليّة. نظام المدرّجات إرث عريق. "
            "هنا فقط ينجح البنّ والفواكه المعتدلة التي تحتاج برودة."
        ),
    },
    "central_highlands": {
        "name_ar": "المرتفعات الوسطى (الهضبة الداخليّة)",
        "governorates_ar": ["صنعاء", "ذمار", "عمران", "صعدة", "البيضاء"],
        "altitude_m": (2000, 3200),
        "temp_c": (5, 25),           # بارد شتاءً (صقيع ممكن)، معتدل صيفاً
        "annual_rain_mm": (200, 400),  # أقلّ من الغربيّة (محميّة بالجبال)
        "humidity_pct": (30, 50),
        "climate_ar": "هضبة مرتفعة، شتاء بارد (صقيع أحياناً)، صيف معتدل، مطر صيفي محدود",
        "water_source_ar": "مطر صيفي محدود + مياه جوفيّة (مستنزفة) + حصاد مياه",
        "suited_crops_ar": [
            "الحبوب (قمح/شعير)", "العنب (شهير في صنعاء)", "الفواكه المعتدلة",
            "البطاطس", "الخضروات الباردة", "البقوليّات", "القات",
        ],
        "avoid_ar": ["المحاصيل الاستوائيّة (مانجو/موز/بابايا)", "محاصيل حسّاسة للصقيع شتاءً"],
        "yemen_note_ar": (
            "صنعاء ~300مم/سنة. الصقيع الشتوي يهدّد المحاصيل — راعِ مواعيد الزراعة. "
            "العنب الصنعاني شهير. خطر استنزاف الخزّان الجوفي حادّ هنا."
        ),
    },
    "eastern_plateau": {
        "name_ar": "الهضبة الشرقيّة شبه الصحراويّة (حضرموت الداخليّة)",
        "governorates_ar": ["وادي حضرموت", "أجزاء من شبوة", "أجزاء من المهرة"],
        "altitude_m": (700, 1200),
        "temp_c": (20, 38),
        "annual_rain_mm": (50, 100),   # جافّ
        "humidity_pct": (35, 64),
        "climate_ar": "جافّ حارّ، وادٍ داخلي واسع بتربة غرينيّة، أمطار نادرة",
        "water_source_ar": "سيول موسميّة في الوديان + مياه جوفيّة",
        "suited_crops_ar": [
            "النخيل (تمور حضرموت الشهيرة)", "الحبوب (قمح/ذرة رفيعة)",
            "الأعلاف", "بعض الخضروات بالريّ",
        ],
        "avoid_ar": ["محاصيل عالية الاحتياج المائي", "محاصيل المرتفعات الباردة"],
        "yemen_note_ar": (
            "وادي حضرموت خصب بمياه السيول والتربة الغرينيّة. تمور حضرموت "
            "استراتيجيّة. الجفاف والحرارة يحدّان الخيارات."
        ),
    },
    "inland_desert": {
        "name_ar": "الصحراء الداخليّة (الجوف/مأرب/أطراف الربع الخالي)",
        "governorates_ar": ["الجوف", "مأرب", "أجزاء صحراويّة شرقيّة"],
        "altitude_m": (600, 1100),
        "temp_c": (20, 42),          # حارّ جدّاً صيفاً
        "annual_rain_mm": (0, 100),    # شحيح جدّاً (قد لا يمطر سنوات)
        "humidity_pct": (30, 60),    # معتدلة (بيانات الحزم الفعليّة: متوسّط ~58%)
        "climate_ar": "صحراوي جافّ، حارّ جدّاً صيفاً، أمطار نادرة جدّاً، رطوبة منخفضة",
        "water_source_ar": "مياه جوفيّة (الاعتماد الأساسي) + سيول نادرة",
        "suited_crops_ar": [
            "النخيل (متحمّل للحرارة والملوحة)", "الحمضيات (بأصول مقاومة)",
            "الذرة الرفيعة/الدخن", "الأعلاف المقاومة (برسيم)", "الرمّان", "العنب",
        ],
        "avoid_ar": [
            "محاصيل عالية الاحتياج المائي (موز)", "محاصيل المرتفعات الباردة",
            "محاصيل حسّاسة للملوحة (الأفوكادو دون أصل مقاوم)",
        ],
        "yemen_note_ar": (
            "الاعتماد شبه الكامل على المياه الجوفيّة — استنزاف خطير. الملوحة "
            "مشكلة محلّيّة في بعض المناطق. اختر محاصيل مقاومة للحرّ/الملوحة/الجفاف."
        ),
    },
    "southern_coast": {
        "name_ar": "الساحل الجنوبي (خليج عدن/بحر العرب)",
        "governorates_ar": ["عدن", "لحج الساحليّة", "أبين", "سواحل حضرموت", "سواحل المهرة"],
        "altitude_m": (0, 200),
        "temp_c": (25, 38),
        "annual_rain_mm": (50, 127),   # شحيح (عدن ~127)
        "humidity_pct": (50, 70),
        "climate_ar": "ساحلي حارّ رطب، أمطار شحيحة، تأثير الرياح الموسميّة (المهرة)",
        "water_source_ar": "سيول الوديان + مياه جوفيّة",
        "suited_crops_ar": [
            "النخيل", "الخضروات الساحليّة", "الذرة الرفيعة", "القطن", "السمسم",
        ],
        "avoid_ar": ["محاصيل المرتفعات الباردة", "محاصيل حسّاسة للرطوبة الساحليّة"],
        "yemen_note_ar": (
            "مشابه لتهامة حرارةً ورطوبةً لكن على بحر العرب. سواحل المهرة تتأثّر "
            "بالرياح الموسميّة (خريف ظفار) فترتفع رطوبتها موسميّاً."
        ),
    },
}

# ربط محافظات/مناطق شائعة بالإقليم (لتحديد الإقليم من اسم المكان)
_LOCATION_TO_ZONE = {
    "الحديدة": "tihama", "تهامة": "tihama", "زبيد": "tihama", "بيت الفقيه": "tihama",
    "تعز": "western_highlands", "إب": "western_highlands", "ريمة": "western_highlands",
    "المحويت": "western_highlands",
    "صنعاء": "central_highlands", "ذمار": "central_highlands", "عمران": "central_highlands",
    "صعدة": "central_highlands", "البيضاء": "central_highlands",
    "حضرموت": "eastern_plateau", "سيئون": "eastern_plateau", "شبام": "eastern_plateau",
    "تريم": "eastern_plateau", "شبوة": "eastern_plateau",
    "الجوف": "inland_desert", "مأرب": "inland_desert",
    "عدن": "southern_coast", "أبين": "southern_coast", "لحج": "southern_coast",
    "المهرة": "southern_coast", "المكلا": "southern_coast",
}


def list_zones() -> Dict:
    """قائمة الأقاليم المناخيّة-الزراعيّة الستّة لليمن مع ملخّصها."""
    return {
        "zones": [
            {
                "zone": k,
                "name_ar": v["name_ar"],
                "governorates_ar": v["governorates_ar"],
                "climate_ar": v["climate_ar"],
                "temp_range_c": list(v["temp_c"]),
                "annual_rain_mm": list(v["annual_rain_mm"]),
            }
            for k, v in _ZONES.items()
        ],
        "count": len(_ZONES),
        "principle_ar": (
            "اليمن 6 أقاليم متمايزة، يحدّد كلٌّ منها ما يُزرع بنجاح. لا توصية "
            "محصول بلا معرفة الإقليم."
        ),
        "source_ar": "تصنيف معتمد (CEFAS) + بيانات الأرصاد والجغرافيا اليمنيّة.",
    }


def zone_profile(zone: str) -> Dict:
    """الملفّ المناخي-الزراعي الكامل لإقليم محدّد."""
    z = _ZONES.get(zone.strip().lower())
    if not z:
        return {"supported": False,
                "message_ar": f"لا إقليم «{zone}». المتاح: "
                              + "، ".join(v["name_ar"] for v in _ZONES.values())}
    return {
        "supported": True,
        "zone": zone,
        "name_ar": z["name_ar"],
        "governorates_ar": z["governorates_ar"],
        "altitude_m": list(z["altitude_m"]),
        "temp_range_c": list(z["temp_c"]),
        "annual_rain_mm": list(z["annual_rain_mm"]),
        "humidity_pct": list(z["humidity_pct"]),
        "climate_ar": z["climate_ar"],
        "water_source_ar": z["water_source_ar"],
        "suited_crops_ar": z["suited_crops_ar"],
        "avoid_ar": z["avoid_ar"],
        "yemen_note_ar": z["yemen_note_ar"],
        "disclaimer_ar": (
            "أرقام تقريبيّة (متوسّطات)؛ التضاريس المحلّيّة تُحدث تبايناً دقيقاً. "
            "استعلم عن منطقتك من هيئة البحوث والإرشاد الزراعي."
        ),
    }


def identify_zone(location: str) -> Dict:
    """يحدّد الإقليم المناخي من اسم محافظة/منطقة."""
    loc = location.strip()
    zone_key = None
    for name, zk in _LOCATION_TO_ZONE.items():
        if name in loc or loc in name:
            zone_key = zk
            break
    if not zone_key:
        return {
            "supported": False,
            "message_ar": (
                f"لم أتعرّف على «{location}». جرّب اسم محافظة معروفة "
                "(الحديدة، تعز، صنعاء، حضرموت، الجوف، عدن…) أو اختر إقليماً مباشرةً."
            ),
            "known_locations_ar": list(_LOCATION_TO_ZONE.keys()),
        }
    prof = zone_profile(zone_key)
    prof["identified_from_ar"] = location
    return prof


def suited_for_zone(zone: str, irrigated: bool = True) -> Dict:
    """المحاصيل الملائمة لإقليم + ما يُتجنّب (مع تنبيه مائي إن لزم)."""
    z = _ZONES.get(zone.strip().lower())
    if not z:
        return {"supported": False,
                "message_ar": f"لا إقليم «{zone}»."}
    rain_max = z["annual_rain_mm"][1]
    rainfed_possible = rain_max >= 400  # بعليّ ممكن فوق ~400مم

    # ربط المناطق العالميّة المشابهة (للصحراء الداخليّة الجافّة فقط)
    from api.climate_analogs import analogs_for_zone
    analogs = analogs_for_zone(zone.strip().lower())

    return {
        "supported": True,
        "zone": zone,
        "name_ar": z["name_ar"],
        "suited_crops_ar": z["suited_crops_ar"],
        "avoid_ar": z["avoid_ar"],
        "rainfed_possible": rainfed_possible,
        "water_note_ar": (
            "زراعة بعليّة ممكنة (أمطار كافية)." if rainfed_possible else
            "زراعة مرويّة ضروريّة (الأمطار لا تكفي) — أدِر الماء بعناية، "
            "راجع وحدتي حصاد المياه وحساسيّة الريّ."
        ),
        "global_analogs_ar": (
            {
                "intro_ar": "مناطق عالميّة مطابقة مناخيّاً أثبتت محاصيل بعينها:",
                **analogs,
            } if analogs.get("applicable") else None
        ),
        "principle_ar": (
            "المحاصيل المقترحة مبنيّة على مناخ الإقليم؛ افحص ملاءمة حقلك المحدّد "
            "(تربة/ملوحة) عبر محرّك الملاءمة قبل القرار."
        ),
        "disclaimer_ar": "توجّه إقليمي عامّ — التربة والصنف المحلّي حاسمان.",
    }


# ─── المحافظات متعدّدة الأقاليم (التضاريس تتجاوز الحدّ الإداري) ───
# هذه محافظات تمتدّ عبر أكثر من إقليم — الاسم وحده لا يكفي، نحتاج الارتفاع.
_MULTI_ZONE_GOVERNORATES = {
    "تعز": {
        "spans_ar": ["western_highlands", "tihama", "southern_coast"],
        "note_ar": (
            "تعز تمتدّ من ساحل المخا الحارّ (تهامة) إلى جبل صبر البارد "
            "(مرتفعات). مديريّة المخا غير مديريّة صبر الموادم مناخيّاً — "
            "حدّد بالارتفاع أو المديريّة."
        ),
        "examples_ar": {
            "المخا": "tihama", "ذباب": "tihama", "موزع": "tihama",
            "صبر الموادم": "western_highlands", "المسراخ": "western_highlands",
            "القاهرة": "western_highlands", "المظفر": "western_highlands", "ماوية": "western_highlands",
        },
    },
    "الحديدة": {
        "spans_ar": ["tihama", "western_highlands"],
        "note_ar": (
            "الحديدة معظمها سهل تهامة الحارّ، لكن مديرياتها الشرقيّة الجبليّة "
            "(الجراحي/باجل المرتفعة) أبرد — حدّد بالارتفاع."
        ),
        "examples_ar": {
            "مدينة الحديدة": "tihama", "زبيد": "tihama", "بيت الفقيه": "tihama",
            "الزيدية": "tihama", "باجل": "tihama", "الحالي": "tihama", "اللحية": "tihama",
        },
    },
    "حضرموت": {
        "spans_ar": ["eastern_plateau", "southern_coast"],
        "note_ar": (
            "حضرموت تنقسم: الوادي الداخلي (هضبة شرقيّة، سيئون/تريم) والساحل "
            "(المكلا، ساحل جنوبي). مناخان مختلفان — حدّد موقعك."
        ),
        "examples_ar": {
            "سيئون": "eastern_plateau", "تريم": "eastern_plateau",
            "شبام": "eastern_plateau", "القطن": "eastern_plateau", "السوم": "eastern_plateau",
            "المكلا": "southern_coast", "الشحر": "southern_coast", "غيل باوزير": "southern_coast",
        },
    },
    "لحج": {
        "spans_ar": ["southern_coast", "western_highlands"],
        "note_ar": (
            "لحج تجمع ساحلاً جنوبيّاً حارّاً ومرتفعات داخليّة (الحبيلين) "
            "أبرد — حدّد بالارتفاع."
        ),
        "examples_ar": {"تبن": "southern_coast", "الحوطة": "southern_coast",
            "الحبيلين": "western_highlands", "ردفان": "western_highlands", "يافع": "western_highlands"},
    },
    "حجة": {
        "spans_ar": ["western_highlands", "tihama"],
        "note_ar": (
            "حجة تجمع مرتفعات جبليّة (مدينة حجة) وسهولاً تهاميّة غربيّة "
            "(عبس/ميدي الحارّة) — حدّد بالارتفاع."
        ),
        "examples_ar": {"مدينة حجة": "western_highlands", "كحلان": "western_highlands", "المحابشة": "western_highlands",
            "عبس": "tihama", "ميدي": "tihama", "حرض": "tihama", "مستباء": "tihama"},
    },
}


def zone_by_elevation(altitude_m: float, is_coastal: bool = False,
                      is_western: bool = True) -> Dict:
    """يحدّد الإقليم بالارتفاع — الأصدق مناخيّاً (المناخ دالّة الارتفاع).

    المزارع يحصل على ارتفاعه من GPS/الخرائط. أدقّ من أيّ اسم إداري.
      is_coastal: قرب البحر (يميّز السهل الساحلي)
      is_western: الجهة الغربيّة (يميّز المرتفعات الغربيّة الممطرة عن الوسطى)
    """
    if altitude_m < 0:
        return {"supported": False, "message_ar": "أدخل ارتفاعاً صحيحاً (متر)."}

    if altitude_m <= 300:
        # سهل ساحلي — غربي (تهامة) أو جنوبي
        zk = "tihama" if is_western else "southern_coast"
    elif altitude_m <= 1000:
        # منخفضات/هضاب منخفضة — صحراء داخليّة أو هضبة شرقيّة
        zk = "inland_desert" if not is_coastal else "southern_coast"
        # ملاحظة: التمييز الدقيق يحتاج موقعاً (شرق=هضبة، شمال=صحراء)
    elif altitude_m <= 1500:
        # انتقالي: الجهة الغربيّة الممطرة → مرتفعات غربيّة (تعز عند 1400م)
        # وإلّا هضبة شرقيّة (وادي حضرموت الداخلي)
        zk = "western_highlands" if is_western else "eastern_plateau"
    else:
        # مرتفعات (>1500م) — غربيّة ممطرة أو وسطى داخليّة
        zk = "western_highlands" if is_western else "central_highlands"

    prof = zone_profile(zk)
    prof["identified_by_ar"] = f"الارتفاع {altitude_m:.0f}م"
    prof["elevation_note_ar"] = (
        "التصنيف بالارتفاع أصدق من الاسم الإداري — المناخ يتبع الارتفاع "
        "والتضاريس لا الحدود. أكّد بمعطيات منطقتك المحدّدة."
    )
    return prof


def identify_zone_v2(location: str, altitude_m: Optional[float] = None,
                     is_western: bool = True) -> Dict:
    """تحديد الإقليم بذكاء: للمحافظات متعدّدة الأقاليم يطلب الارتفاع/المديريّة.

    أصدق من identify_zone للمحافظات الجبليّة-الساحليّة (كتعز).
    """
    loc = location.strip()

    # ١) مديريّة معروفة داخل أيّ محافظة متعدّدة الأقاليم؟ (نبحث المديريّات أوّلاً)
    for gov, info in _MULTI_ZONE_GOVERNORATES.items():
        for sub, zk in info["examples_ar"].items():
            if sub in loc or loc in sub:
                prof = zone_profile(zk)
                prof["identified_from_ar"] = f"{location} (مديريّة في {gov})"
                return prof

    # ٢) اسم محافظة متعدّدة الأقاليم وحدها (بلا مديريّة)؟
    for gov, info in _MULTI_ZONE_GOVERNORATES.items():
        if gov in loc or loc in gov:
            if altitude_m is not None:
                return zone_by_elevation(altitude_m, is_western=is_western)
            return {
                "supported": False,
                "multi_zone": True,
                "governorate_ar": gov,
                "spans_ar": [_ZONES[z]["name_ar"] for z in info["spans_ar"]],
                "message_ar": (
                    f"محافظة {gov} تمتدّ عبر أكثر من إقليم مناخي. {info['note_ar']} "
                    "أدخل اسم المديريّة أو ارتفاعها (متر) للتحديد الدقيق."
                ),
                "example_districts_ar": info["examples_ar"],
            }

    # ٣) محافظة أحاديّة الإقليم — التحديد المباشر
    return identify_zone(location)
