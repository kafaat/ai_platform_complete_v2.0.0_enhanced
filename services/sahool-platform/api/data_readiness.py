"""
api/data_readiness.py — محرّك اكتمال البيانات

مُستلهَم من هرميّة البيانات (المستند ٩)، مُكيّف بصدق: يأخذ ما أدخله المزارع
ويحدّد بشفافيّة:
  • أيّ مستوى بيانات بلغ (١ أساسي → ٧ تراثي)
  • أيّ توصيات مُتاحة الآن، وأيّها محجوب
  • ما البيانات التالية الأعلى أثراً لإضافتها

يجسّد فلسفة سهول: "النظام يعمل بأقلّ المدخلات" + التدرّج + الصدق (لا ندّعي
دقّة لا تدعمها البيانات). يكمّل confidence_gate.

⚠ نسب الدقّة التقديريّة (٧٠-٩٠٪) من المستند ٩ — موسومة كتقدير إرشادي لا وعد.
"""

from __future__ import annotations

from dataclasses import dataclass

# المستويات وحقولها (من هرميّة المستند ٩، مُكيّفة لحقول سهول)
DATA_LEVELS: list[dict] = [
    {
        "level": 1,
        "name_ar": "بيانات الحقل الأساسيّة",
        "mandatory": True,
        "fields": ["location", "area_ha", "crop", "season", "planting_date", "irrigation"],
    },
    {
        "level": 2,
        "name_ar": "المناخ والطقس",
        "mandatory": True,
        "fields": ["t_min", "t_max", "rain"],  # يكفي للـHargreaves
    },
    {
        "level": 3,
        "name_ar": "التربة الأساسيّة",
        "mandatory": True,
        "fields": ["soil_texture", "ph", "ec"],
    },
    {
        "level": 4,
        "name_ar": "المؤشّرات النباتيّة",
        "mandatory": False,
        "fields": ["ndvi"],  # NDRE/MSAVI اختياريّة
    },
    {
        "level": 5,
        "name_ar": "تحاليل مختبريّة (NPK + ميكرو)",
        "mandatory": False,
        "fields": ["n_ppm", "p_ppm", "k_ppm", "fe_ppm", "zn_ppm"],
    },
    {
        "level": 6,
        "name_ar": "مستشعرات حقليّة",
        "mandatory": False,
        "fields": ["soil_moisture"],
    },
    {
        "level": 7,
        "name_ar": "بيانات تاريخيّة/سياقيّة",
        "mandatory": False,
        "fields": ["prev_yield", "prev_season_data"],
    },
]

# أيّ توصية تتطلّب أيّ بيانات (الحدّ الأدنى)
RECOMMENDATION_REQUIREMENTS: dict[str, dict] = {
    "irrigation": {  # ميزان الماء
        "name_ar": "توصية الريّ",
        "requires": {"t_min", "t_max", "crop"},
        "improved_by": {"ndvi", "soil_moisture", "rain"},
    },
    "nitrogen_advisory": {  # 4R نيتروجين (إرشادي)
        "name_ar": "إرشاد النيتروجين",
        "requires": {"crop", "ph"},
        "improved_by": {"n_ppm", "ndvi"},
    },
    "phosphorus": {  # 4R فوسفور — يحتاج مختبر
        "name_ar": "توصية الفوسفور",
        "requires": {"p_ppm"},  # محجوب دون Olsen-P
        "improved_by": set(),
    },
    "micronutrients": {  # Fe/Zn — يحتاج مختبر
        "name_ar": "توصية المغذّيات الدقيقة",
        "requires": {"fe_ppm"},
        "improved_by": {"zn_ppm"},
    },
    "zones": {  # مناطق NDVI
        "name_ar": "مناطق الإدارة",
        "requires": {"ndvi"},
        "improved_by": set(),
    },
    "crop_suitability": {  # ملاءمة المحاصيل
        "name_ar": "ملاءمة المحاصيل",
        "requires": {"soil_texture", "ph", "ec"},
        "improved_by": {"rain", "t_max"},
    },
}

# تقدير الدقّة الإرشادي حسب أعلى مستوى مُحقَّق (المستند ٩ — تقدير لا وعد)
_ACCURACY_HINT = {
    3: "٧٠-٨٠٪ (تقدير أوّلي)",
    4: "٨٠-٨٥٪ (مع المؤشّرات)",
    5: "٩٠٪+ (مع تحاليل مختبر)",
}


@dataclass
class ReadinessResult:
    highest_complete_level: int
    levels_status: list[dict]
    available_recommendations: list[str]
    blocked_recommendations: list[dict]
    next_best_data_ar: list[str]
    accuracy_hint_ar: str

    def to_dict(self) -> dict:
        return {
            "highest_complete_level": self.highest_complete_level,
            "levels_status": self.levels_status,
            "available_recommendations": self.available_recommendations,
            "blocked_recommendations": self.blocked_recommendations,
            "next_best_data_ar": self.next_best_data_ar,
            "accuracy_hint_ar": self.accuracy_hint_ar,
        }


def assess_readiness(provided: list[str]) -> ReadinessResult:
    """يقيّم اكتمال البيانات بناءً على الحقول المتوفّرة.

    Args:
        provided: قائمة أسماء الحقول المتوفّرة فعلاً للحقل.
    """
    have: set[str] = set(provided)

    # حالة كلّ مستوى
    levels_status = []
    highest_complete = 0
    for lvl in DATA_LEVELS:
        present = [f for f in lvl["fields"] if f in have]
        complete = len(present) == len(lvl["fields"])
        levels_status.append(
            {
                "level": lvl["level"],
                "name_ar": lvl["name_ar"],
                "mandatory": lvl["mandatory"],
                "complete": complete,
                "present": present,
                "missing": [f for f in lvl["fields"] if f not in have],
            }
        )
        if complete:
            highest_complete = lvl["level"]

    # أيّ توصيات متاحة / محجوبة
    available = []
    blocked = []
    next_data: set[str] = set()
    for key, req in RECOMMENDATION_REQUIREMENTS.items():
        missing_req = req["requires"] - have
        if not missing_req:
            available.append(key)
            # ما الذي يحسّنها لكنّه ناقص؟
            next_data |= req["improved_by"] - have
        else:
            blocked.append(
                {
                    "recommendation": key,
                    "name_ar": req["name_ar"],
                    "missing_ar": _fields_ar(missing_req),
                }
            )
            next_data |= missing_req

    # مستوى أعلى من أعلى مفتاح (مثلاً 6 بمجسّات) يأخذ تلميح أعلى دقّة (5)، لا "" —
    # كان «بيانات أكثر ⇒ تلميح أفرغ» (عكسيّ). نقصّ المفتاح لأعلى تلميح مُعرَّف.
    if highest_complete >= min(_ACCURACY_HINT):
        accuracy = _ACCURACY_HINT[min(highest_complete, max(_ACCURACY_HINT))]
    else:
        accuracy = "محدودة (بيانات ناقصة)"

    return ReadinessResult(
        highest_complete_level=highest_complete,
        levels_status=levels_status,
        available_recommendations=available,
        blocked_recommendations=blocked,
        next_best_data_ar=_fields_ar(next_data),
        accuracy_hint_ar=accuracy,
    )


_FIELD_AR = {
    "location": "الموقع",
    "area_ha": "المساحة",
    "crop": "المحصول",
    "season": "الموسم",
    "planting_date": "تاريخ الزراعة",
    "irrigation": "نظام الريّ",
    "t_min": "الحرارة الصغرى",
    "t_max": "الحرارة العظمى",
    "rain": "المطر",
    "soil_texture": "نسيج التربة",
    "ph": "حموضة التربة (pH)",
    "ec": "ملوحة التربة (EC)",
    "ndvi": "مؤشّر NDVI",
    "n_ppm": "نيتروجين مختبري",
    "p_ppm": "فوسفور Olsen-P",
    "k_ppm": "بوتاسيوم مختبري",
    "fe_ppm": "حديد مختبري",
    "zn_ppm": "زنك مختبري",
    "soil_moisture": "رطوبة التربة (مستشعر)",
    "prev_yield": "إنتاج سابق",
    "prev_season_data": "بيانات موسم سابق",
}


def _fields_ar(fields) -> list[str]:
    return [_FIELD_AR.get(f, f) for f in sorted(fields)]
