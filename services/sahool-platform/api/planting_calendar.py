"""
api/planting_calendar.py — تقويم مواعيد الزراعة المثلى (محاصيل اليمن)

جانب جديد عملي: التبكير أو التأخير في الزراعة يسبّب مشاكل حقيقيّة. مثلاً
الذرة الشاميّة المتأخّرة (بعد منتصف يونيو) تتعرّض بشدّة لدودة الحشد الخريفيّة.
القمح يجب أن يُزرع في نافذته وإلّا تأثّر الإنبات والإنتاج.

هذا يكمّل:
  • التقويم النجمي (astronomical_timing): مرساة موسميّة تراثيّة عامّة
  • هذا الملفّ: نوافذ زراعة محصوليّة محدّدة بالأشهر + تحذيرات التبكير/التأخير

⚠ النوافذ تقريبيّة من أدبيّات زراعيّة + سياق اليمن. تختلف حسب الارتفاع
(المرتفعات أبرد، تهامة أحرّ) والصنف. توجّه لا تفرض — المزارع يعرف دقائق أرضه.
السياق اليمني: الزراعة البعليّة تتبع الأمطار الموسميّة، والمرويّة أكثر مرونة.
"""
from __future__ import annotations

from typing import Dict, List, Optional


# نوافذ الزراعة (بالأشهر الميلاديّة) لمحاصيل اليمن الرئيسيّة
# month_window = (شهر البداية، شهر النهاية)؛ optimal = الأشهر المثلى داخلها
_PLANTING: Dict[str, Dict] = {
    "wheat": {
        "name_ar": "القمح",
        "season_ar": "شتوي",
        "window_months": [11, 12, 1],        # نوفمبر–يناير
        "optimal_months": [11, 12],
        "harvest_months": [4, 5],
        "early_risk_ar": "التبكير قبل نوفمبر: حرارة عالية قد تضرّ الإنبات.",
        "late_risk_ar": "التأخير بعد يناير: نقص فترة النموّ وتأثّر الإنتاج.",
        "yemen_note_ar": "الجوف والمرتفعات. الموسم الشتوي يستفيد من برودة وأمطار محدودة.",
    },
    "barley": {
        "name_ar": "الشعير",
        "season_ar": "شتوي",
        "window_months": [10, 11, 12, 1],
        "optimal_months": [11, 12],
        "harvest_months": [3, 4],
        "early_risk_ar": "التبكير المفرط مع حرارة عالية.",
        "late_risk_ar": "التأخير يقصّر موسم النموّ.",
        "yemen_note_ar": "المرتفعات الباردة والترب المالحة — أكثر تحمّلاً من القمح.",
    },
    "maize": {
        "name_ar": "الذرة الشاميّة",
        "season_ar": "صيفي",
        "window_months": [3, 4, 5, 6],       # مارس–يونيو
        "optimal_months": [4, 5],
        "harvest_months": [7, 8, 9],
        "early_risk_ar": "التبكير (مارس): فرص إصابة مرضيّة وحشرات (المنّ).",
        "late_risk_ar": (
            "⚠ التأخير بعد منتصف يونيو: ارتفاع حادّ لإصابة دودة الحشد الخريفيّة "
            "وصعوبة مكافحتها → خسارة كبيرة."
        ),
        "yemen_note_ar": "تهامة والجوف صيفاً. يمكن زراعتها عقب حصاد القمح الشتوي.",
    },
    "sorghum": {
        "name_ar": "الذرة الرفيعة",
        "season_ar": "صيفي/مطري",
        "window_months": [4, 5, 6, 7],
        "optimal_months": [5, 6],
        "harvest_months": [9, 10, 11],
        "early_risk_ar": "قبل بدء الأمطار الموسميّة (للزراعة البعليّة).",
        "late_risk_ar": "التأخير يعرّضها لنقص رطوبة آخر الموسم.",
        "yemen_note_ar": "تهامة والمناطق المطريّة. مقاومة جفاف، تتبع موسم الأمطار.",
    },
    "millet": {
        "name_ar": "الدخن",
        "season_ar": "صيفي/مطري",
        "window_months": [5, 6, 7],
        "optimal_months": [6, 7],
        "harvest_months": [9, 10],
        "early_risk_ar": "قبل استقرار الأمطار.",
        "late_risk_ar": "التأخير يقصّر النافذة المطريّة.",
        "yemen_note_ar": "أراضٍ هامشيّة قليلة المطر. دورة قصيرة تتبع الأمطار.",
    },
}

_ALIASES = {
    "قمح": "wheat", "شعير": "barley", "ذرة شامية": "maize", "ذرة شاميّة": "maize",
    "ذرة رفيعة": "sorghum", "دخن": "millet",
}

_MONTH_AR = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


def _resolve(crop: str) -> Optional[str]:
    c = crop.strip().lower()
    if c in _PLANTING:
        return c
    return _ALIASES.get(crop.strip())


def _months_ar(months: List[int]) -> str:
    return "، ".join(_MONTH_AR[m] for m in months)


def supported_crops() -> List[Dict]:
    return [
        {"crop": k, "name_ar": v["name_ar"], "season_ar": v["season_ar"],
         "window_ar": _months_ar(v["window_months"])}
        for k, v in _PLANTING.items()
    ]


def planting_window(crop: str) -> Dict:
    """نافذة الزراعة الكاملة لمحصول + المخاطر + السياق اليمني."""
    key = _resolve(crop)
    if not key:
        return {"supported": False,
                "message_ar": f"لا تقويم زراعة لـ«{crop}». المدعوم: "
                              + "، ".join(v["name_ar"] for v in _PLANTING.values())}
    c = _PLANTING[key]
    return {
        "supported": True,
        "crop": key, "crop_ar": c["name_ar"], "season_ar": c["season_ar"],
        "window_months": c["window_months"],
        "window_ar": _months_ar(c["window_months"]),
        "optimal_ar": _months_ar(c["optimal_months"]),
        "harvest_ar": _months_ar(c["harvest_months"]),
        "early_risk_ar": c["early_risk_ar"],
        "late_risk_ar": c["late_risk_ar"],
        "yemen_note_ar": c["yemen_note_ar"],
        "disclaimer_ar": (
            "نوافذ تقريبيّة تختلف حسب الارتفاع (المرتفعات أبرد، تهامة أحرّ) "
            "والصنف. توجّه لا تفرض."
        ),
    }


def check_planting_date(crop: str, month: int) -> Dict:
    """يقيّم: هل الشهر الحالي مناسب لزراعة هذا المحصول؟"""
    key = _resolve(crop)
    if not key:
        return {"supported": False, "message_ar": f"المحصول «{crop}» غير مدعوم."}
    if not 1 <= month <= 12:
        return {"supported": False, "message_ar": "الشهر يجب أن يكون 1-12."}

    c = _PLANTING[key]
    window, optimal = c["window_months"], c["optimal_months"]

    if month in optimal:
        status, status_ar = "optimal", "✓ موعد مثالي"
        advice = f"{_MONTH_AR[month]} ضمن النافذة المثلى لزراعة {c['name_ar']}."
    elif month in window:
        status, status_ar = "acceptable", "مقبول"
        advice = f"{_MONTH_AR[month]} ضمن النافذة لكن ليس الأمثل. النافذة المثلى: {_months_ar(optimal)}."
    else:
        status, status_ar = "off_window", "⚠ خارج النافذة"
        # حدّد إن كان تبكيراً أم تأخيراً (تقريبي عبر القرب من البداية/النهاية)
        before = month < window[0]
        risk = c["early_risk_ar"] if before else c["late_risk_ar"]
        advice = (
            f"{_MONTH_AR[month]} خارج نافذة زراعة {c['name_ar']} ({_months_ar(window)}). "
            + risk
        )

    return {
        "supported": True,
        "crop_ar": c["name_ar"],
        "month_ar": _MONTH_AR[month],
        "status": status, "status_ar": status_ar,
        "advice_ar": advice,
        "optimal_ar": _months_ar(optimal),
        "yemen_note_ar": c["yemen_note_ar"],
    }
