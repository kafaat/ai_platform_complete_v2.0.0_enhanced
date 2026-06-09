"""
api/crop_water_sensitivity.py — حساسيّة المراحل للإجهاد المائي (محاصيل اليمن)

يكمّل ميزان الماء (water_balance.py): لا يكفي حساب الاحتياج، بل معرفة **متى**
يكون نقص الماء كارثيّاً. مبني على مراجع علميّة (FAO-56 + WikiFarmer + دراسات).

يغطّي المحاصيل اليمنيّة الرئيسيّة (الحبوب = 47% من المساحة المزروعة):
  • القمح (wheat) — شتوي، الجوف/الهضبة
  • الذرة الشاميّة (maize) — صيفي، أكثر المحاصيل زراعةً، غذاء + علف
  • الذرة الرفيعة (sorghum) — مقاومة جفاف عالية، تهامة، عيدانها علف
  • الدخن (millet) — مقاوم جفاف، أراضٍ هامشيّة
  • الشعير (barley) — يتحمّل الملوحة والجفاف والمرتفعات

⚠ القيم إرشاديّة من مراجع عالميّة — تحتاج معايرة محلّيّة يمنيّة. الإرشاد
يوجّه القرار، لا يقرّر آليّاً (human-in-the-loop). نغطّي ما لدينا مرجع له فقط.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class WaterSensitivity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


# ════════════════════════════════════════════════════════════════
# سجلّ المحاصيل: لكلّ محصول مراحله + حساسيّتها + سياقه اليمني
# ════════════════════════════════════════════════════════════════
_CROPS: Dict[str, Dict] = {
    "wheat": {
        "name_ar": "القمح",
        "season_total_mm": "350-600",
        "season_ar": "شتوي (يُزرع خريفاً، يُحصد أواخر الربيع)",
        "drought_tolerance_ar": "متوسّط",
        "critical_window_ar": "من الاستطالة حتى الإزهار = ~70% من الاحتياج",
        "irrigation_frequency_ar": "4-6 ريّات؛ كل 12-18 يوماً في الأراضي الجافة المرويّة",
        "yemen_context_ar": "الجوف والهضاب، ريّ محوري من المياه الجوفيّة الشحيحة.",
        "stages": [
            ("germination", "الإنبات", WaterSensitivity.HIGH, 10,
             "نقص الماء قد يُفشل المحصول. ريّ مبكر (~150مم) لإنبات متناسق."),
            ("tillering", "الإشطاء", WaterSensitivity.MODERATE, 15,
             "ازدياد الطلب مع نمو الأوراق."),
            ("stem_elongation", "الاستطالة (الصعود)", WaterSensitivity.CRITICAL, 25,
             "بداية المرحلة الأحرج. ⚠ التشبّع المائي هنا كارثي (خسارة حتى 92%)."),
            ("flowering", "الإزهار", WaterSensitivity.CRITICAL, 20,
             "ذروة الحساسيّة. قد يلزم ريّ تكميلي 90-150مم."),
            ("grain_filling", "تكوين الحبوب", WaterSensitivity.HIGH, 20,
             "النقص يقلّل عدد ووزن الحبوب وامتصاص النيتروجين."),
            ("maturity", "النضج", WaterSensitivity.LOW, 10,
             "أوقف الريّ تدريجيّاً قبل الحصاد."),
        ],
    },
    "maize": {
        "name_ar": "الذرة الشاميّة",
        "season_total_mm": "500-800",
        "season_ar": "صيفي (يحتاج ~90 يوماً، جوّ حارّ مشمس)",
        "drought_tolerance_ar": "متوسّط (يحتاج ريّاً منتظماً)",
        "critical_window_ar": "التزهير والتلقيح (ظهور النورة والحريرة) = الأحرج",
        "irrigation_frequency_ar": "6-7 ريّات منتظمة؛ الرية الأولى خفيفة (نشع لا غمر)",
        "yemen_context_ar": (
            "أكثر المحاصيل زراعةً في اليمن — غذاء (خبز/لحوح/عصيدة) وعلف (العيدان 70% "
            "من علف المواشي). تهامة والجوف صيفاً."
        ),
        "stages": [
            ("emergence", "الإنبات والظهور", WaterSensitivity.HIGH, 12,
             "رطوبة كافية ضروريّة عند ظهور النباتات. الرية الأولى خفيفة."),
            ("vegetative", "النمو الخضري", WaterSensitivity.MODERATE, 20,
             "نمو سريع، طلب متزايد على الماء."),
            ("tasseling", "التزهير والتلقيح", WaterSensitivity.CRITICAL, 30,
             "⚠ الأحرج: نقص الماء عند التلقيح يقلّل عدد الحبوب بشدّة (فراغات بالكوز)."),
            ("grain_filling", "امتلاء الحبوب", WaterSensitivity.HIGH, 28,
             "يحدّد وزن الحبّة. النقص يقلّل الإنتاج."),
            ("maturity", "النضج", WaterSensitivity.LOW, 10,
             "قلّل الريّ تدريجيّاً."),
        ],
    },
    "sorghum": {
        "name_ar": "الذرة الرفيعة (الذرة)",
        "season_total_mm": "300-500",
        "season_ar": "صيفي/مطري بشكل رئيسي",
        "drought_tolerance_ar": "عالٍ جدّاً (من أكثر الحبوب تحمّلاً للجفاف)",
        "critical_window_ar": "من طرد السنابل حتى الإزهار",
        "irrigation_frequency_ar": "محصول مطري غالباً؛ ريّ تكميلي عند الحاجة فقط",
        "yemen_context_ar": (
            "محصول تقليدي مقاوم للجفاف، عيدانه علف رئيسي. تهامة والمناطق الهامشيّة. "
            "يعتمد على الأمطار غالباً — ميزته أنّه يصمد حيث يفشل غيره."
        ),
        "stages": [
            ("emergence", "الإنبات", WaterSensitivity.MODERATE, 15,
             "يتحمّل جفافاً أكثر من القمح/الذرة الشاميّة."),
            ("vegetative", "النمو الخضري", WaterSensitivity.LOW, 25,
             "مرحلة متحمّلة — قدرته على الجفاف عالية هنا."),
            ("booting_flowering", "طرد السنابل والإزهار", WaterSensitivity.CRITICAL, 35,
             "⚠ الأحرج رغم تحمّله العام — النقص هنا يقلّل المحصول."),
            ("grain_filling", "امتلاء الحبوب", WaterSensitivity.HIGH, 20,
             "ريّ تكميلي مفيد إن توفّر."),
            ("maturity", "النضج", WaterSensitivity.LOW, 5, "لا حاجة لريّ."),
        ],
    },
    "millet": {
        "name_ar": "الدخن",
        "season_total_mm": "300-450",
        "season_ar": "صيفي/مطري، دورة قصيرة",
        "drought_tolerance_ar": "عالٍ جدّاً (من أكثر الحبوب مقاومةً للجفاف والحرارة)",
        "critical_window_ar": "الإزهار وامتلاء الحبوب",
        "irrigation_frequency_ar": "مطري غالباً؛ ريّ تكميلي نادر",
        "yemen_context_ar": (
            "حبوب تقليديّة للأراضي الهامشيّة قليلة المطر. يصمد في ظروف يفشل فيها "
            "غيره. غذاء وعلف. مناسب لمناطق اليمن الجافّة جدّاً."
        ),
        "stages": [
            ("emergence", "الإنبات", WaterSensitivity.MODERATE, 18,
             "يحتاج رطوبة للإنبات ثمّ يتحمّل."),
            ("vegetative", "النمو الخضري", WaterSensitivity.LOW, 27,
             "متحمّل جدّاً للجفاف."),
            ("flowering", "الإزهار", WaterSensitivity.HIGH, 30,
             "أحرج مرحلة — النقص يقلّل عقد الحبوب."),
            ("grain_filling", "امتلاء الحبوب", WaterSensitivity.MODERATE, 20,
             "ريّ تكميلي مفيد إن توفّر."),
            ("maturity", "النضج", WaterSensitivity.LOW, 5, "لا حاجة لريّ."),
        ],
    },
    "barley": {
        "name_ar": "الشعير",
        "season_total_mm": "300-450",
        "season_ar": "شتوي",
        "drought_tolerance_ar": "عالٍ (يتحمّل الجفاف والملوحة والبرد أكثر من القمح)",
        "critical_window_ar": "من الاستطالة حتى الإزهار (شبيه القمح)",
        "irrigation_frequency_ar": "3-5 ريّات؛ أقلّ من القمح",
        "yemen_context_ar": (
            "يتحمّل المرتفعات والبرد والملوحة. بديل للقمح في الأراضي الأصعب "
            "والترب المالحة. مهمّ للمرتفعات اليمنيّة."
        ),
        "stages": [
            ("germination", "الإنبات", WaterSensitivity.HIGH, 12,
             "رطوبة ضروريّة للإنبات."),
            ("tillering", "الإشطاء", WaterSensitivity.MODERATE, 18,
             "أكثر تحمّلاً من القمح."),
            ("stem_elongation", "الاستطالة", WaterSensitivity.CRITICAL, 25,
             "⚠ بداية المرحلة الأحرج."),
            ("flowering", "الإزهار", WaterSensitivity.CRITICAL, 25,
             "ذروة الحساسيّة."),
            ("grain_filling", "امتلاء الحبوب", WaterSensitivity.HIGH, 15,
             "النقص يقلّل وزن الحبوب."),
            ("maturity", "النضج", WaterSensitivity.LOW, 5, "أوقف الريّ."),
        ],
    },
}

# مرادفات عربيّة → مفتاح إنجليزي
_ALIASES = {
    "قمح": "wheat", "ذرة شامية": "maize", "ذرة شاميّة": "maize", "شامية": "maize",
    "ذرة رفيعة": "sorghum", "ذرة": "sorghum", "رفيعة": "sorghum",
    "دخن": "millet", "شعير": "barley",
}


def _resolve(crop: str) -> Optional[str]:
    c = crop.strip().lower()
    if c in _CROPS:
        return c
    return _ALIASES.get(crop.strip())


@dataclass
class StageSensitivity:
    stage_key: str
    name_ar: str
    sensitivity: WaterSensitivity
    water_share_pct: int
    note_ar: str
    is_critical_window: bool

    def to_dict(self) -> Dict:
        return {
            "stage_key": self.stage_key, "name_ar": self.name_ar,
            "sensitivity": self.sensitivity.value,
            "water_share_pct": self.water_share_pct,
            "note_ar": self.note_ar, "is_critical_window": self.is_critical_window,
        }


def supported_crops() -> List[Dict]:
    """قائمة المحاصيل المدعومة (للعرض)."""
    return [
        {
            "crop": k, "name_ar": v["name_ar"],
            "drought_tolerance_ar": v["drought_tolerance_ar"],
            "season_ar": v["season_ar"],
        }
        for k, v in _CROPS.items()
    ]


def get_stage_sensitivity(crop: str, stage_key: str) -> Optional[StageSensitivity]:
    key = _resolve(crop)
    if not key:
        return None
    for sk, name, sens, share, note in _CROPS[key]["stages"]:
        if sk == stage_key:
            crit = sens in (WaterSensitivity.CRITICAL, WaterSensitivity.HIGH)
            return StageSensitivity(sk, name, sens, share, note, crit)
    return None


def water_calendar(crop: str) -> Dict:
    """التقويم المائي الكامل لمحصول (كلّ المراحل + السياق اليمني)."""
    key = _resolve(crop)
    if not key:
        return {
            "supported": False,
            "message_ar": f"لا بيانات حساسيّة مائيّة لـ«{crop}». المدعوم: "
                          + "، ".join(v["name_ar"] for v in _CROPS.values()),
        }
    c = _CROPS[key]
    return {
        "supported": True,
        "crop": key,
        "crop_ar": c["name_ar"],
        "season_total_mm": c["season_total_mm"],
        "season_ar": c["season_ar"],
        "drought_tolerance_ar": c["drought_tolerance_ar"],
        "critical_window_ar": c["critical_window_ar"],
        "irrigation_frequency_ar": c["irrigation_frequency_ar"],
        "yemen_context_ar": c["yemen_context_ar"],
        "moderate_stress_threshold_ar": "يبدأ الإجهاد المعتدل عند نضوب التربة فوق 70%",
        "stages": [
            get_stage_sensitivity(key, sk).to_dict()  # type: ignore
            for sk, *_ in c["stages"]
        ],
        "disclaimer_ar": (
            "قيم إرشاديّة من مراجع عالميّة (FAO-56، WikiFarmer، دراسات منشورة). "
            "تحتاج معايرة محلّيّة. الإرشاد يوجّه، لا يستبدل خبرة المزارع."
        ),
    }


def assess_stress_risk(crop: str, stage_key: str, depletion_pct: float) -> Dict:
    """يقيّم خطر الإجهاد بناءً على المرحلة ونضوب التربة."""
    ss = get_stage_sensitivity(crop, stage_key)
    if not ss:
        return {
            "supported": False,
            "message_ar": f"لا بيانات لـ«{crop}» مرحلة «{stage_key}». "
                          "المدعوم: قمح، ذرة شاميّة، ذرة رفيعة، دخن، شعير.",
        }
    if depletion_pct >= 80:
        level, level_ar = "severe", "إجهاد شديد"
    elif depletion_pct >= 70:
        level, level_ar = "moderate", "إجهاد معتدل"
    else:
        level, level_ar = "ok", "ضمن الأمان"
    urgent = ss.is_critical_window and depletion_pct >= 60
    return {
        "supported": True,
        "crop_ar": _CROPS[_resolve(crop)]["name_ar"],  # type: ignore
        "stage_ar": ss.name_ar,
        "sensitivity": ss.sensitivity.value,
        "is_critical_window": ss.is_critical_window,
        "depletion_pct": depletion_pct,
        "stress_level": level,
        "stress_level_ar": level_ar,
        "urgent_irrigation": urgent,
        "advice_ar": (
            f"⚠ {ss.name_ar}: مرحلة حرجة + نضوب {depletion_pct:.0f}% → اروِ قريباً "
            "لتفادي خسارة كبيرة."
            if urgent else
            f"{ss.name_ar}: {level_ar} عند نضوب {depletion_pct:.0f}%. "
            + (ss.note_ar if level != "ok" else "تابع المراقبة.")
        ),
    }


# توافق خلفي: الدالّة القديمة wheat_water_calendar
def wheat_water_calendar() -> Dict:
    d = water_calendar("wheat")
    d["warning_waterlogging_ar"] = (
        "التشبّع المائي ضارّ كالجفاف: خسارة حتى 92% من الاستطالة للإزهار، "
        "وارتفاع منسوب الماء الجوفي (<0.5م) يخفض المحصول 20-40%."
    )
    return d


def integrated_irrigation_advice(
    crop: str, stage_key: str, depletion_pct: float,
    net_irrigation_mm: Optional[float] = None,
) -> Dict:
    """توصية ريّ متكاملة: تجمع الحساسيّة (متى حرج) مع الاحتياج (كم).

    تربط crop_water_sensitivity مع ناتج water_balance لتعطي المزارع صورة
    كاملة: المرحلة + حرجيّتها + نضوب التربة + الاحتياج المائي + قرار عملي.
    """
    risk = assess_stress_risk(crop, stage_key, depletion_pct)
    if not risk.get("supported"):
        return risk

    out = dict(risk)
    if net_irrigation_mm is not None:
        out["net_irrigation_mm"] = round(net_irrigation_mm, 1)
        # وسم القرينة للتظافر: ميزان الماء = نموذج حسابي (crop_model)
        # يتظافر مع الاستشعار والملاحظة الميدانيّة، لا يرجّح وحده
        out["evidence_type"] = "crop_model"
        out["corroboration_note_ar"] = (
            "هذه توصية نموذج حسابي (FAO-56). تتأكّد إن وافقها مؤشّر الاستشعار "
            "(NDVI) أو ملاحظتك الميدانيّة. النموذج وحده توجيهي."
        )
        # دمج القرار: الحرجيّة + الاحتياج
        if risk["urgent_irrigation"] and net_irrigation_mm > 0:
            out["integrated_advice_ar"] = (
                f"🚨 {risk['stage_ar']} (مرحلة حرجة) + نضوب {depletion_pct:.0f}% + احتياج "
                f"{net_irrigation_mm:.0f}مم → اروِ الآن بهذه الكميّة لحماية المحصول."
            )
        elif net_irrigation_mm == 0:
            out["integrated_advice_ar"] = (
                f"{risk['stage_ar']}: المطر يغطّي الاحتياج حاليّاً. "
                + ("راقب — المرحلة حرجة." if risk["is_critical_window"] else "تابع.")
            )
        else:
            out["integrated_advice_ar"] = (
                f"{risk['stage_ar']}: احتياج {net_irrigation_mm:.0f}مم، "
                f"{risk['stress_level_ar']}. "
                + ("المرحلة حرجة — لا تؤجّل." if risk["is_critical_window"] else "ضمن المعتاد.")
            )
    return out
