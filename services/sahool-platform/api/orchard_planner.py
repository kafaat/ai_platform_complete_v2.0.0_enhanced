"""
api/orchard_planner.py — مخطّط البستان المختلط الاستثماري (لوز/زيتون/فستق)

جانب جديد: للمناطق الصحراويّة (الجوف/الحزم)، أفضل نموذج استثماري ليس محصولاً
واحداً بل **بستان مختلط** يوازن: عائد سريع (لوز) + استقرار (زيتون) + ربح عالٍ
طويل الأمد (فستق). يقلّل المخاطرة ويوزّع التدفّق النقدي عبر الزمن.

يحسب: توزيع الأشجار + الكثافة + المسافات + جدول العائد الزمني + ملاحظات الريّ.

المصادر (موثّقة بالبحث):
  • الفستق: 6×6م ≈ 272 شجرة/هكتار، ذكر لكلّ 8-10 إناث، إنتاج 6-10 كجم/شجرة
    عند النضج (7-10 سنوات)، عمر اقتصادي 30-50 سنة (Wikifarmer + American Pistachios)
  • الزيتون: كثافة عالية ممكنة، يبدأ 3-5 سنوات (Olive Oil Source + Frontiers)
  • اللوز: 200-400 شجرة/هكتار، يبدأ 3-4 سنوات (أسرع عائد)

⚠ تحذير جوهري للمناطق الجافّة (مؤكّد بحثيّاً): الكثافة العالية تسبّب تنافساً
شديداً على الماء وتخفض الإنتاج — لا تكثّف في الصحراء. الأرقام الاقتصاديّة
تقديريّة جدّاً وتتذبذب بشدّة مع السوق/الإدارة/الملوحة — ليست وعداً بل سيناريو.
القرار النهائي يحتاج دراسة جدوى ميدانيّة + خبير زراعي + تحليل بئر فعلي.
"""
from __future__ import annotations

from typing import Dict, List, Optional


# نماذج الأشجار الصحراويّة (أرقام موثّقة — تقديريّة محافظة)
_TREE_PROFILES = {
    "اللوز": {
        "role_ar": "محرّك التدفّق النقدي المبكّر",
        "spacing_m": "5×5", "trees_per_ha": 200,
        "first_yield_year": 4, "full_yield_year": 7,
        "water_ar": "متوسّط", "risk_ar": "متوسّطة",
        "note_ar": "أسرع عائداً (3-4 سنوات)؛ توازن السرعة والربح",
    },
    "الزيتون": {
        "role_ar": "الاستقرار طويل الأمد",
        "spacing_m": "6×6", "trees_per_ha": 280,
        "first_yield_year": 4, "full_yield_year": 8,
        "water_ar": "منخفض (الأكثر تحمّلاً)", "risk_ar": "منخفضة",
        "note_ar": "الأكثر أماناً وتحمّلاً للجفاف والملوحة؛ سوق أسهل",
    },
    "الفستق": {
        "role_ar": "الربح العالي طويل الأمد",
        "spacing_m": "6×6", "trees_per_ha": 270,
        "first_yield_year": 7, "full_yield_year": 13,
        "water_ar": "متوسّط (حسّاس للملوحة والتشبّع)", "risk_ar": "عالية",
        "note_ar": "أعلى ربح لكن عائد بطيء (7-10 سنوات) + ذكر لكلّ 8-10 إناث",
    },
}

# المزيج الموصى به للمناطق الصحراويّة (نسب موثّقة من نماذج استثماريّة)
_RECOMMENDED_MIX = {"اللوز": 0.50, "الزيتون": 0.30, "الفستق": 0.20}


def mixed_orchard_plan(area_ha: float = 1.0,
                       mix: Optional[Dict[str, float]] = None) -> Dict:
    """يخطّط بستاناً مختلطاً صحراويّاً: توزيع + كثافة + جدول عائد زمني.

    area_ha: المساحة بالهكتار. mix: نسب المحاصيل (افتراضي 50 لوز/30 زيتون/20 فستق).
    """
    if area_ha <= 0:
        return {"supported": False, "message_ar": "أدخل مساحة موجبة بالهكتار."}
    ratios = mix or _RECOMMENDED_MIX
    total_ratio = sum(ratios.values())
    if abs(total_ratio - 1.0) > 0.01:
        return {"supported": False,
                "message_ar": f"مجموع النسب يجب أن يساوي 1.0 (الحالي {total_ratio})."}

    blocks = []
    cash_flow_timeline: Dict[int, List[str]] = {}
    for crop, ratio in ratios.items():
        prof = _TREE_PROFILES.get(crop)
        if not prof:
            continue
        crop_area = area_ha * ratio
        n_trees = int(crop_area * prof["trees_per_ha"])
        males_note = ""
        if crop == "الفستق":
            males = max(1, n_trees // 9)  # ذكر لكلّ 8-10 إناث
            males_note = f" (منها ~{males} ذكر للتلقيح)"
        blocks.append({
            "crop_ar": crop,
            "role_ar": prof["role_ar"],
            "area_ha": round(crop_area, 2),
            "trees": n_trees,
            "males_note_ar": males_note,
            "spacing_m": prof["spacing_m"],
            "first_yield_year": prof["first_yield_year"],
            "full_yield_year": prof["full_yield_year"],
            "water_ar": prof["water_ar"],
            "risk_ar": prof["risk_ar"],
            "note_ar": prof["note_ar"],
        })
        cash_flow_timeline.setdefault(prof["first_yield_year"], []).append(
            f"{crop} يبدأ الإنتاج")
        cash_flow_timeline.setdefault(prof["full_yield_year"], []).append(
            f"{crop} إنتاج كامل")

    timeline_sorted = [
        {"year": y, "events_ar": cash_flow_timeline[y]}
        for y in sorted(cash_flow_timeline)
    ]

    return {
        "supported": True,
        "area_ha": area_ha,
        "model_ar": "بستان مختلط صحراوي (Agroforestry Investment Mix)",
        "philosophy_ar": (
            "ليس محصولاً واحداً بل مزيج يوازن: عائد سريع (لوز) + استقرار "
            "(زيتون) + ربح عالٍ طويل الأمد (فستق). يقلّل المخاطرة ويوزّع التدفّق "
            "النقدي عبر الزمن."
        ),
        "blocks": blocks,
        "total_trees": sum(b["trees"] for b in blocks),
        "cash_flow_timeline_ar": timeline_sorted,
        "layout_advice_ar": (
            "قسّم الأرض إلى بلوكات ريّ منفصلة، كلّ بلوك نوع واحد (يسهّل إدارة "
            "الريّ المختلف لكلّ محصول). ممرّات خدمة 3-4م."
        ),
        "irrigation_ar": (
            "ريّ بالتنقيط ضروري (تنقيط مزدوج الخطّ). الفستق حسّاس جدّاً للتشبّع "
            "(الريّ الزائد يقتل جذوره) والملوحة (راقب EC<2000ppm). الزيتون "
            "الأكثر تحمّلاً. افصل جدولة الريّ لكلّ بلوك."
        ),
        "arid_warning_ar": (
            "⚠ لا تكثّف الأشجار في الصحراء: الكثافة العالية تسبّب تنافساً شديداً "
            "على الماء وتخفض الإنتاج (مؤكّد بحثيّاً للمناطق الجافّة). الكثافات "
            "هنا محافظة ومناسبة لشحّ الماء."
        ),
        "strategy_ar": (
            "ابدأ باللوز (عائد سريع) + الزيتون (استقرار)، وأدخل الفستق تدريجيّاً "
            "(لا تبدأ بالفستق وحده — مخاطرة عالية وعائد بطيء 7-10 سنوات)."
        ),
        "disclaimer_ar": (
            "تخطيط إرشادي بأرقام موثّقة عامّة. الأرقام الفعليّة (عائد/تكلفة) تتذبذب "
            "بشدّة مع السوق والإدارة والملوحة والصنف — ليست وعداً. تحتاج دراسة "
            "جدوى ميدانيّة + خبير زراعي + تحليل بئرك الفعلي قبل الاستثمار."
        ),
    }


def orchard_economics_note(area_ha: float = 1.0) -> Dict:
    """ملاحظات اقتصاديّة تقديريّة للبستان المختلط (تقريبيّة جدّاً — سيناريو لا وعد)."""
    if area_ha <= 0:
        return {"supported": False, "message_ar": "أدخل مساحة موجبة."}
    # نطاقات تقديريّة واسعة (دولار) — تتناسب خطّيّاً مع المساحة
    return {
        "supported": True,
        "area_ha": area_ha,
        "establishment_usd_range": [round(4000 * area_ha), round(8000 * area_ha)],
        "establishment_breakdown_ar": {
            "تجهيز الأرض": [round(800 * area_ha), round(1500 * area_ha)],
            "الشتلات": [round(1200 * area_ha), round(2500 * area_ha)],
            "نظام الريّ بالتنقيط": [round(1500 * area_ha), round(3000 * area_ha)],
            "تسميد وتحسين تربة": [round(500 * area_ha), round(1000 * area_ha)],
        },
        "annual_income_stages_ar": [
            {"years": "1-3", "usd_range": [0, round(500 * area_ha)],
             "note_ar": "تأسيس — إنتاج محدود من اللوز"},
            {"years": "3-5", "usd_range": [round(800 * area_ha), round(2500 * area_ha)],
             "note_ar": "اللوز يبدأ + بعض الزيتون"},
            {"years": "5-7", "usd_range": [round(2000 * area_ha), round(6000 * area_ha)],
             "note_ar": "زيتون + لوز قويّ + بداية الفستق"},
            {"years": "8-15", "usd_range": [round(5000 * area_ha), round(15000 * area_ha)],
             "note_ar": "إنتاج كامل مستقرّ"},
        ],
        "high_risks_ar": ["نقص المياه", "ملوحة التربة", "بطء عائد الفستق",
                          "تقلّبات السوق"],
        "disclaimer_ar": (
            "⚠ أرقام تقديريّة واسعة جدّاً (سيناريو لا وعد). تتأثّر بشدّة بالسوق "
            "والإدارة والملوحة وجودة البئر. استشر خبير جدوى زراعيّة قبل أيّ "
            "قرار استثماري. لا تعتمد هذه الأرقام وحدها."
        ),
    }
