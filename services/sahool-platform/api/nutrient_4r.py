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

from core.thresholds import HIGH_PH_THRESHOLD


class Nutrient(str, Enum):
    N = "nitrogen"
    P = "phosphorus"
    K = "potassium"
    FE = "iron"
    ZN = "zinc"


class RecommendationStatus(str, Enum):
    OK = "ok"  # توصية جاهزة
    BLOCKED = "blocked"  # محجوبة — تحتاج تحليل مختبر
    ADVISORY = "advisory"  # إرشاد عام بلا معدّل دقيق


@dataclass
class SoilContext:
    """سياق التربة (من تحليل مختبري لو متاح)."""

    caco3_pct: float | None = None  # كربونات الكالسيوم
    ph: float | None = None
    p_ppm: float | None = None  # فوسفور متاح
    fe_ppm: float | None = None
    zn_ppm: float | None = None
    om_pct: float | None = None  # مادة عضويّة


@dataclass
class FourRRecommendation:
    """توصية 4R لعنصر واحد."""

    nutrient: Nutrient
    status: RecommendationStatus
    source_ar: str  # right Source
    rate_ar: str  # right Rate
    timing_ar: str  # right Time
    placement_ar: str  # right Place
    warnings_ar: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
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
_HIGH_PH_THRESHOLD = HIGH_PH_THRESHOLD  # قلويّة (المصدر الموحّد core.thresholds)
# قيمة مجهولة ليست صفراً: غياب CaCO3/pH لا يستبعد الخطر، فيُفترَض قائماً (تحذير محافظ).
_UNKNOWN_SOIL_RISK_WARNING = (
    "CaCO3/pH غير معروف — افترض وجود الخطر (CaCO3/pH unknown — assume risk)"
)


def recommend_nitrogen(soil: SoilContext) -> FourRRecommendation:
    """قاعدة N للتربة الكلسيّة: تجنّب تطاير الأمونيا."""
    warnings = []
    is_calc = soil.caco3_pct is not None and soil.caco3_pct >= _CALCAREOUS_THRESHOLD
    high_ph = soil.ph is not None and soil.ph >= _HIGH_PH_THRESHOLD

    source = "كبريتات الأمونيوم أو نترات (أفضل من اليوريا في التربة الكلسيّة)"
    if is_calc or high_ph:
        warnings.append("خطر تطاير الأمونيا عالٍ — تجنّب نثر اليوريا على السطح")
    elif soil.caco3_pct is None or soil.ph is None:
        warnings.append(_UNKNOWN_SOIL_RISK_WARNING + " — خطر تطاير الأمونيا")

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
    is_calc = soil.caco3_pct is not None and soil.caco3_pct >= _CALCAREOUS_THRESHOLD

    if soil.p_ppm is None:
        # absence-of-authority → BLOCKED (مبدأ حاكم)
        return FourRRecommendation(
            nutrient=Nutrient.P,
            status=RecommendationStatus.BLOCKED,
            source_ar="—",
            rate_ar="محجوب: يلزم تحليل مختبري للفوسفور المتاح (Olsen-P)",
            timing_ar="—",
            placement_ar="—",
            warnings_ar=["لا توصية بمعدّل P دون تحليل مختبر — الفوسفور يُثبَّت بشدّة في التربة الكلسيّة"],
        )

    warnings = []
    if is_calc:
        warnings.append("تثبيت الفوسفور مرتفع — الحزم قرب الجذور أكفأ من النثر بكثير")
    elif soil.caco3_pct is None:
        warnings.append(_UNKNOWN_SOIL_RISK_WARNING + " — خطر تثبيت الفوسفور")
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
    chelate = (
        "مخلّبي (Fe-EDDHA يقاوم التربة الكلسيّة)"
        if nutrient == Nutrient.FE
        else "كبريتات الزنك أو مخلّبي"
    )

    if val is None:
        return FourRRecommendation(
            nutrient=nutrient,
            status=RecommendationStatus.BLOCKED,
            source_ar="—",
            rate_ar=f"محجوب: يلزم تحليل {name}",
            timing_ar="—",
            placement_ar="—",
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


# ─── منحنى امتصاص العنصر عبر المراحل (Nutrient Uptake Curve) ────────────────────
# يربط الاحتياج الكلّيّ (crop_demand_kg_ha من fertilizer.compute) بتوزيعه الزمنيّ:
# الامتصاص ليس خطّيّاً — بطيء بدئيّاً، يبلغ ذروته في مرحلة النموّ الفعّال/الإزهار،
# ثمّ يتباطأ أواخر الموسم. هذا يحوّل "كم سماد" إلى "متى" (Right Time في 4R).
#
# ترتيب المراحل من _STAGE_FRACTIONS (مصدر موحّد) — أمّا نِسَب الامتصاص فمستقلّة عن
# أطوال المراحل (الامتصاص مدفوع بالكتلة الحيويّة لا بالزمن).
# ⚠ نِسَب أوّليّة من شكل منحنى الامتصاص العامّ (أدبيّات) — تحتاج معايرة يمنيّة لكلّ
# محصول/عنصر. موسومة calibrated=False. Σ=1.0. **احتياط فقط**: محصولٌ تحمل بطاقته منحنى
# ``phenology.stages[].nutrient_demand`` يُقرأ منحناه أوّلاً (``nutrient_uptake``).
_UPTAKE_FRACTIONS: dict[str, float] = {
    "initial": 0.10,
    "development": 0.35,
    "mid": 0.40,
    "late": 0.15,
}


def _stage_order() -> list[str]:
    """ترتيب المراحل من المصدر الموحّد في season_simulation."""
    from api.season_simulation import _STAGE_FRACTIONS

    return [name for name, _ in _STAGE_FRACTIONS]


def _stage_length_bounds() -> list[tuple[str, float, float]]:
    """حدود التقدّم [start, end] لكلّ مرحلة من أطوالها النسبيّة (لتفسير progress)."""
    from api.season_simulation import _STAGE_FRACTIONS

    bounds: list[tuple[str, float, float]] = []
    acc = 0.0
    for name, length in _STAGE_FRACTIONS:
        bounds.append((name, acc, acc + length))
        acc += length
    return bounds


_NUTRIENT_KEYS: dict[str, str] = {
    "n": "n",
    "nitrogen": "n",
    "p": "p",
    "phosphorus": "p",
    "k": "k",
    "potassium": "k",
}


def _card_uptake_curve(
    crop: str | None, element: str
) -> tuple[list[tuple[str, float, float, float]], str | None, str | None]:
    """منحنى امتصاص العنصر من بطاقة المحصول: [(مرحلة، كسر، بداية، نهاية)] بتقدّم [0,1].

    الكسور مشتقّة لنوافذ FAO-56 في البطاقة نفسها (``phenology.stages``)، فحدود التقدّم
    تُؤخذ من أيّام تلك النوافذ لا من الأطوال العامّة — كسرٌ يُطبَّق على نافذةٍ غير التي
    اشتُقّ لها يُزيح الجرعة زمنيّاً. يُرجِع ([], None, سبب) إن لا منحنى صالحاً.
    """
    from core.crop_cards.loader import stage_nutrient_demand
    from core.season_phenology import resolve_crop_id

    crop_id = resolve_crop_id(crop)
    if crop_id is None:
        return [], None, None
    stages = stage_nutrient_demand(crop_id)
    if not stages:
        return [], crop_id, None
    names = [st["stage"] for st in stages]
    fracs = [st.get(f"{element}_fraction") for st in stages]
    total_days = max(float(st["day_end"]) for st in stages)
    if (
        names != _stage_order()
        or not all(isinstance(f, (int, float)) and f >= 0 for f in fracs)
        or abs(sum(fracs) - 1.0) > 0.01
        or total_days <= 0
    ):
        return [], crop_id, "منحنى البطاقة غير صالح (مراحل/مجموع كسور) — استُعمل المنحنى العامّ"
    curve = [
        (
            st["stage"],
            float(f),
            float(st["day_start"]) / total_days,
            float(st["day_end"]) / total_days,
        )
        for st, f in zip(stages, fracs, strict=True)
    ]
    return curve, crop_id, None


def _generic_uptake_curve() -> list[tuple[str, float, float, float]]:
    return [
        (name, _UPTAKE_FRACTIONS.get(name, 0.0), start, end)
        for name, start, end in _stage_length_bounds()
    ]


def nutrient_uptake(
    crop: str | None,
    stage_or_progress: str | float | None,
    target_uptake_kg_ha: float,
    nutrient: str = "n",
) -> dict:
    """يوزّع الاحتياج الكلّيّ من عنصر على منحنى الامتصاص عبر المراحل — نقيّ حتميّ.

    المدخلات:
      • crop: يُحلّ إلى بطاقة المحصول؛ منحنى البطاقة المرحليّ للعنصر (``nutrient_demand``)
        يُقرأ أوّلاً (``source: crop_card``)، وإلّا المنحنى العامّ (``source: generic``).
      • stage_or_progress: اسم مرحلة (تراكم *شامل* لها)، أو تقدّم موسمي [0,1]
        (استيفاء خطّيّ عبر حدود المراحل)، أو None (المنحنى الكامل بلا "حتى الآن").
      • target_uptake_kg_ha: الاحتياج الموسمي الكلّيّ (مثلاً crop_demand_kg_ha من
        fertilizer.compute). سالب أو صفر ⇒ كمّيّات صفريّة (لا تلفيق).
      • nutrient: العنصر الذي يخصّه الهدف (n/p/k؛ الافتراض n).

    المخرجات (dict): المنحنى لكلّ مرحلة + التراكم "حتى الآن" + المصدر + calibrated=False.
    صدق: لا منحنى معايَر محلّيّاً (منحنى البطاقة تقريب أدبيّ، والعامّ أقلّ منه)؛ عند غياب
    الهدف لا نخترع رقماً.
    """
    element = _NUTRIENT_KEYS.get((nutrient or "").strip().lower())
    if element is None:
        raise ValueError(f"عنصر غير مدعوم لمنحنى الامتصاص: {nutrient!r} (n/p/k)")
    curve, crop_id, card_warning = _card_uptake_curve(crop, element)
    if curve:
        source = "crop_card"
        warnings_ar: list[str] = [
            "منحنى امتصاص البطاقة تقريب أدبيّ غير معايَر محلّيّاً — الكسور تقديريّة",
        ]
    else:
        source = "generic"
        curve = _generic_uptake_curve()
        warnings_ar = [
            "منحنى امتصاص عامّ غير معايَر يمنيّاً — النِّسَب تقديريّة لكلّ محصول/عنصر",
        ]
        if card_warning:
            warnings_ar.append(card_warning)
    target = max(0.0, float(target_uptake_kg_ha or 0.0))
    if target_uptake_kg_ha is not None and target_uptake_kg_ha < 0:
        warnings_ar.append("هدف الامتصاص سالب — عومل كصفر")

    stages: list[dict] = []
    cum_frac = 0.0
    cum_kg = 0.0
    for name, frac, _start, _end in curve:
        kg = frac * target
        cum_frac += frac
        cum_kg += kg
        stages.append(
            {
                "stage": name,
                "stage_fraction": round(frac, 4),
                "uptake_kg_ha": round(kg, 2),
                "cumulative_fraction": round(cum_frac, 4),
                "cumulative_kg_ha": round(cum_kg, 2),
            }
        )

    # التراكم "حتى الآن" حسب نوع stage_or_progress.
    to_date_fraction = 0.0
    matched_stage: str | None = None
    if isinstance(stage_or_progress, str):
        key = stage_or_progress.strip().lower()
        if key in {name for name, *_ in curve}:
            matched_stage = key
            for name, frac, _start, _end in curve:
                to_date_fraction += frac
                if name == key:
                    break
        else:
            warnings_ar.append(f"مرحلة غير معروفة ({stage_or_progress}) — التراكم حتى الآن=0")
    elif isinstance(stage_or_progress, (int, float)) and not isinstance(stage_or_progress, bool):
        p = min(1.0, max(0.0, float(stage_or_progress)))
        for name, frac, start, end in curve:
            if p >= end:
                to_date_fraction += frac
                matched_stage = name
            elif p > start:
                span = end - start
                portion = (p - start) / span if span > 0 else 1.0
                to_date_fraction += frac * portion
                matched_stage = name
                break
            else:
                break

    to_date_fraction = min(1.0, to_date_fraction)
    return {
        "crop": (crop or "").strip().lower() or None,
        "crop_id": crop_id,
        "nutrient": element,
        "source": source,
        "target_uptake_kg_ha": round(target, 2),
        "stages": stages,
        "matched_stage": matched_stage,
        "cumulative_fraction_to_date": round(to_date_fraction, 4),
        "uptake_to_date_kg_ha": round(to_date_fraction * target, 2),
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }


def full_4r_plan(soil: SoilContext, nutrients: list[str] | None = None) -> list[dict]:
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
