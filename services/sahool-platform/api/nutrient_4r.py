"""
api/nutrient_4r.py — قواعد 4R للتسميد في التربة الكلسيّة اليمنيّة

خارطة الطريق: المرحلة ٢، البند ١٣.

التربة اليمنيّة كلسيّة (CaCO3 22-36٪، قلويّة عالية). هذا يجعل تسميد النيتروجين
والفوسفور مختلفاً جوهريّاً:
  • اليوريا تتحلّل بسرعة و pH موقع التفاعل يرتفع >8.2 → تطاير الأمونيا
  • الفوسفور يُثبَّت (غير متاح) → الحزم قرب الجذور أفضل من النثر
  • الحديد والزنك يصبحان غير متاحَين → تصحيح ورقي

إطار 4R (right Source / Rate / Time / Place — مرجع IPNI/Mosaic):
نُرجمه لقواعد عمليّة. المبدأ الحاكم: "الاستشعار يوجّه / المختبر يحكم" —
NDVI يحدّد المنطقة، لكنّ المعدّل يبقى BLOCKED حتى توفّر تحليل مختبري للـP/Fe/Zn.

⚠ القيم الإرشاديّة من أدبيّات التربة الكلسيّة (FAO + مراجع)، لكنّها تحتاج
معايرة محلّيّة. موسومة. هذا محرّك قواعد لا ثوابت إنتاج.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Nutrient(str, Enum):
    N = "nitrogen"
    P = "phosphorus"
    K = "potassium"
    FE = "iron"
    ZN = "zinc"


class RecommendationStatus(str, Enum):
    OK = "ok"                  # توصية جاهزة
    BLOCKED = "blocked"        # محجوبة — تحتاج تحليل مختبر
    ADVISORY = "advisory"      # إرشاد عام بلا معدّل دقيق


@dataclass
class SoilContext:
    """سياق التربة (من تحليل مختبري لو متاح)."""
    caco3_pct: Optional[float] = None       # كربونات الكالسيوم
    ph: Optional[float] = None
    p_ppm: Optional[float] = None           # فوسفور متاح
    fe_ppm: Optional[float] = None
    zn_ppm: Optional[float] = None
    om_pct: Optional[float] = None          # مادة عضويّة


@dataclass
class FourRRecommendation:
    """توصية 4R لعنصر واحد."""
    nutrient: Nutrient
    status: RecommendationStatus
    source_ar: str        # right Source
    rate_ar: str          # right Rate
    timing_ar: str        # right Time
    placement_ar: str     # right Place
    warnings_ar: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "nutrient": self.nutrient.value,
            "status": self.status.value,
            "source_ar": self.source_ar,
            "rate_ar": self.rate_ar,
            "timing_ar": self.timing_ar,
            "placement_ar": self.placement_ar,
            "warnings_ar": self.warnings_ar,
        }


# عتبة CaCO3 التي تُفعّل تحذيرات التربة الكلسيّة (أدبيّات التربة)
_CALCAREOUS_THRESHOLD = 15.0  # %
_HIGH_PH_THRESHOLD = 7.8


def recommend_nitrogen(soil: SoilContext) -> FourRRecommendation:
    """قاعدة N للتربة الكلسيّة: تجنّب تطاير الأمونيا."""
    warnings = []
    is_calc = (soil.caco3_pct or 0) >= _CALCAREOUS_THRESHOLD
    high_ph = (soil.ph or 0) >= _HIGH_PH_THRESHOLD

    source = "كبريتات الأمونيوم أو نترات (أفضل من اليوريا في التربة الكلسيّة)"
    if is_calc or high_ph:
        warnings.append("خطر تطاير الأمونيا عالٍ — تجنّب نثر اليوريا على السطح")

    return FourRRecommendation(
        nutrient=Nutrient.N,
        status=RecommendationStatus.ADVISORY,  # المعدّل يحتاج هدف إنتاج/تحليل
        source_ar=source,
        rate_ar="جزّئ الجرعة على دفعتَين-ثلاث (لا دفعة واحدة) لتقليل الفقد",
        timing_ar="ادفع N مع مراحل النموّ النشطة، لا قبلها بكثير",
        placement_ar="ادفن/احقن تحت السطح (banding) بدل النثر — يقلّل التطاير",
        warnings_ar=warnings,
    )


def recommend_phosphorus(soil: SoilContext) -> FourRRecommendation:
    """قاعدة P: الفوسفور مُثبَّت في التربة الكلسيّة → BLOCKED بلا تحليل."""
    is_calc = (soil.caco3_pct or 0) >= _CALCAREOUS_THRESHOLD

    if soil.p_ppm is None:
        # absence-of-authority → BLOCKED (مبدأ حاكم)
        return FourRRecommendation(
            nutrient=Nutrient.P,
            status=RecommendationStatus.BLOCKED,
            source_ar="—", rate_ar="محجوب: يلزم تحليل مختبري للفوسفور المتاح (Olsen-P)",
            timing_ar="—", placement_ar="—",
            warnings_ar=["لا توصية بمعدّل P دون تحليل مختبر — الفوسفور يُثبَّت بشدّة في التربة الكلسيّة"],
        )

    warnings = []
    if is_calc:
        warnings.append("تثبيت الفوسفور مرتفع — الحزم قرب الجذور أكفأ من النثر بكثير")
    low_p = soil.p_ppm < 10  # عتبة Olsen-P تقريبيّة
    return FourRRecommendation(
        nutrient=Nutrient.P,
        status=RecommendationStatus.OK if not low_p else RecommendationStatus.ADVISORY,
        source_ar="سوبر فوسفات أو DAP",
        rate_ar=("منخفض" if not low_p else "مرتفع") + f" (Olsen-P = {soil.p_ppm} ppm)",
        timing_ar="عند الزراعة (الفوسفور بطيء الحركة)",
        placement_ar="احزم قرب البذرة/الجذر (banding) — لا تنثر في التربة الكلسيّة",
        warnings_ar=warnings,
    )


def recommend_micronutrient(soil: SoilContext, nutrient: Nutrient) -> FourRRecommendation:
    """قاعدة Fe/Zn: غير متاحَين في التربة الكلسيّة → تصحيح ورقي."""
    val = soil.fe_ppm if nutrient == Nutrient.FE else soil.zn_ppm
    name = "الحديد" if nutrient == Nutrient.FE else "الزنك"
    chelate = "مخلّبي (Fe-EDDHA يقاوم التربة الكلسيّة)" if nutrient == Nutrient.FE else "كبريتات الزنك أو مخلّبي"

    if val is None:
        return FourRRecommendation(
            nutrient=nutrient,
            status=RecommendationStatus.BLOCKED,
            source_ar="—", rate_ar=f"محجوب: يلزم تحليل {name}",
            timing_ar="—", placement_ar="—",
            warnings_ar=[f"{name} شائع النقص في التربة الكلسيّة لكن لا معدّل دون تحليل"],
        )

    return FourRRecommendation(
        nutrient=nutrient,
        status=RecommendationStatus.ADVISORY,
        source_ar=chelate,
        rate_ar=f"حسب شدّة النقص ({name} = {val} ppm)",
        timing_ar="رشّ ورقي عند ظهور أعراض الاصفرار بين العروق",
        placement_ar="رشّ ورقي (التطبيق الأرضي غير فعّال — يُثبَّت فوراً)",
        warnings_ar=["التطبيق الأرضي للحديد/الزنك يُهدَر في التربة الكلسيّة — الرشّ الورقي أكفأ"],
    )


def full_4r_plan(soil: SoilContext, nutrients: Optional[List[str]] = None) -> List[Dict]:
    """خطة 4R كاملة لقائمة عناصر (افتراضي: N, P, Fe, Zn — شائعة النقص يمنيّاً)."""
    if nutrients is None:
        nutrients = ["nitrogen", "phosphorus", "iron", "zinc"]
    out = []
    for n in nutrients:
        nut = Nutrient(n)
        if nut == Nutrient.N:
            out.append(recommend_nitrogen(soil).to_dict())
        elif nut == Nutrient.P:
            out.append(recommend_phosphorus(soil).to_dict())
        elif nut in (Nutrient.FE, Nutrient.ZN):
            out.append(recommend_micronutrient(soil, nut).to_dict())
    return out
