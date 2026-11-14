"""تحليل جودة ماء الريّ — مؤشّرات قياسيّة (SAR/RSC/تصنيف الملوحة).

الفجوة (من سياق الصُنيدر): لا تحليل ماء ريّ رغم اشتباهه محرّكاً للملوحة
والقلويّة المرصودتين في التربة. هذه الوحدة تحسب المؤشّرات الزراعيّة القياسيّة
من بيانات مخبريّة تُدخَل — منطق علمي حقيقي قابل للاختبار، يُستخدَم فور توفّر
تحليل مخبري (لا جدول DB فارغ، لا بيانات مفبركة).

المراجع (FAO-29 / USDA Bulletin 197 / Eaton 1950):
- SAR = Na / √((Ca + Mg)/2)   [الأيونات بـmeq/L]
- RSC = (CO₃ + HCO₃) − (Ca + Mg)   [meq/L]  (Eaton 1950)
- تصنيف الملوحة بـEC (dS/m) — FAO-29

العتبات (موثّقة):
- RSC: <1.25 آمن، 1.25–2.50 هامشي، >2.50 غير مناسب (USDA Bull. 197)
- SAR: <10 منخفض، 10–18 متوسّط، 18–26 مرتفع، >26 مرتفع جدّاً (USSL)
  (مشاكل النفاذيّة تبدأ SAR 6–9 في التربة الطينيّة المنتفخة)
- EC: <0.7 لا قيود، 0.7–3.0 قيود طفيفة إلى متوسّطة، >3.0 قيود شديدة (FAO-29)
- النفاذيّة (FAO-29): SAR يُقرأ مع ECw معاً — جدول ``FAO29_INFILTRATION_ROWS``

الحكم العامّ بثلاث درجات قيود كما في FAO-29 (None / Slight-to-moderate / Severe):
``suitable`` (لا قيود) · ``suitable_with_restrictions`` (قيود طفيفة إلى متوسّطة، تُسمّى
المؤشّرات المسبِّبة ودرجتها) · ``needs_treatment`` (قيود شديدة) · ``insufficient_data``.

صدق: لا يخترع بيانات. المدخل الناقص يُعلَن (None/تحذير)؛ لا تصنيف بلا قيم.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Literal, get_args

# نوع مصدر ماء الريّ: مفردات عقد قاعدة البيانات نفسها — CHECK على
# ``irrigation_water_sources.source_type`` في migrations/v168_irrigation_engineering_foundation.sql.
# لا «mixed»: الخليط في العقد ليس نوع مصدر، بل عدّة مصادر بنسب مزج
# (``field_irrigation_source_assignments.mixing_ratio``، v214) تُحسَب جودته بـ``compute_blend_water_quality``.
# عيّنةٌ أُخذت من خطّ خليط تُسجَّل ``other``.
WaterSourceType = Literal["well", "reservoir", "canal", "river", "municipal", "rainwater", "other"]
WATER_SOURCE_TYPES: tuple[str, ...] = get_args(WaterSourceType)


@dataclass
class WaterSample:
    """عيّنة ماء ريّ مخبريّة. الأيونات بـmeq/L، EC بـdS/m، pH بلا وحدة.

    صدق: كلّ الحقول اختياريّة (قد لا يقيس المختبر كلّ شيء)؛ المؤشّر الذي يحتاج
    قيمة غائبة يُعلَن غير محسوب (لا تقدير مفبرَك).
    """

    sample_id: str
    # يُتحقَّق منه عند حدّ API (Pydantic) وفي النواة (invalid_water_inputs).
    source: WaterSourceType = "well"
    # الأيونات (meq/L)
    na: float | None = None  # صوديوم
    ca: float | None = None  # كالسيوم
    mg: float | None = None  # مغنيسيوم
    hco3: float | None = None  # بيكربونات
    co3: float | None = None  # كربونات
    cl: float | None = None  # كلوريد
    # القياسات العامّة
    ec_dsm: float | None = None  # التوصيليّة الكهربائيّة dS/m
    ph: float | None = None
    sampled_at: str | None = None

    def __post_init__(self) -> None:
        # مدخل مستحيل فيزيائيّاً (EC سالبة، أيون سالب، pH خارج 0–14، NaN/inf) يُرفض
        # عند المدخل — لا يُصنَّف «لا قيود». ValueError ⇒ 422 في طبقة API.
        errors = invalid_water_inputs(self)
        if errors:
            raise ValueError("invalid water sample: " + ", ".join(errors))


_WATER_ION_FIELDS = ("na", "ca", "mg", "hco3", "co3", "cl")


def invalid_water_inputs(sample: WaterSample) -> list[str]:
    """Reject impossible measurements and unknown source kinds at the core boundary."""
    errors: list[str] = []
    # A source kind is not a verified well/canal identity; never accept field names as kinds.
    # One vocabulary: WATER_SOURCE_TYPES (v168), the same Literal the API and the UI use.
    if sample.source not in WATER_SOURCE_TYPES:
        errors.append("source:unsupported_kind")
    for fname in (*_WATER_ION_FIELDS, "ec_dsm", "ph"):
        value = getattr(sample, fname)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            errors.append(f"{fname}:not_a_number")
            continue
        try:
            finite = math.isfinite(value)
        except (OverflowError, ValueError):
            errors.append(f"{fname}:out_of_float_range")
            continue
        if not finite:
            errors.append(f"{fname}:not_finite")
        elif value < 0:
            errors.append(f"{fname}:negative")
        elif fname == "ph" and value > 14:
            errors.append("ph:out_of_range")
    return errors


# أسباب «غير قابل للحساب» مع وجود كلّ المدخلات (تختلف عن نقص المدخل في missing_inputs):
# مدخلاتٌ منتهية كلٌّ على حدة قد يفيض جمعها أو نسبتها إلى inf، فينتج SAR = 0 «منخفض» مزيّف
# أو RSC = inf − inf = NaN لا يُسلسَل JSON. الحساب يفشل مغلقاً (None) ويُعلَن السبب.
WATER_NUMERIC_OVERFLOW = "WATER-NUMERIC-OVERFLOW"
REASON_NUMERIC_OVERFLOW = "numeric_overflow"
REASON_CA_MG_ZERO = "calcium_plus_magnesium_zero"


def sar_with_reason(na, ca, mg) -> tuple[float | None, str | None]:
    """Stable SAR, including finite inputs whose naive Ca+Mg intermediate overflows."""
    if na is None or ca is None or mg is None:
        return None, None
    if any(not _finite_non_negative(v) for v in (na, ca, mg)):
        return None, REASON_NUMERIC_OVERFLOW
    # Convert *before* arithmetic: arbitrary-size Python integers also reach this core API.
    na, ca, mg = float(na), float(ca), float(mg)
    total = ca + mg
    if total == 0:
        return None, REASON_CA_MG_ZERO
    if math.isfinite(total):
        # sqrt(total)/sqrt(2) preserves subnormal contributions lost by total/2.
        root = math.sqrt(total) / math.sqrt(2.0)
    else:
        # Halving both non-negative terms before addition avoids overflow.
        root = math.sqrt(ca / 2.0 + mg / 2.0)
    sar = na / root
    if not math.isfinite(sar):
        return None, REASON_NUMERIC_OVERFLOW
    return round(sar, 2), None


def rsc_with_reason(co3, hco3, ca, mg) -> tuple[float | None, str | None]:
    """Stable RSC: fsum for normal values, exact-float Decimal fallback for overflow."""
    vals = (co3, hco3, ca, mg)
    if any(v is None for v in vals):
        return None, None
    if any(not _finite_non_negative(v) for v in vals):
        return None, REASON_NUMERIC_OVERFLOW
    carbonates, bicarbonates, calcium, magnesium = (float(v) for v in vals)
    try:
        rsc = math.fsum((carbonates, bicarbonates, -calcium, -magnesium))
    except OverflowError:
        # math.fsum can overflow its intermediate even when the true final sum is 0.
        with localcontext() as ctx:
            ctx.prec = 1200  # Enough for exact decimal expansion of binary64 values.
            c, h, ca_dec, mg_dec = (
                Decimal.from_float(v) for v in (carbonates, bicarbonates, calcium, magnesium)
            )
            exact = (c + h) - (ca_dec + mg_dec)
        rsc = float(exact)
    if not math.isfinite(rsc):
        return None, REASON_NUMERIC_OVERFLOW
    return round(rsc, 2), None


def compute_sar(na: float, ca: float, mg: float) -> float | None:
    """SAR = Na / √((Ca+Mg)/2). الأيونات meq/L. None إن نقص مدخل أو تعذّر حسابه."""
    return sar_with_reason(na, ca, mg)[0]


def compute_rsc(co3: float, hco3: float, ca: float, mg: float) -> float | None:
    """RSC = (CO₃ + HCO₃) − (Ca + Mg) بالـmeq/L (Eaton 1950). None إن نقص أو تعذّر."""
    return rsc_with_reason(co3, hco3, ca, mg)[0]


_NOT_COMPUTABLE_NOTE_AR = {
    REASON_NUMERIC_OVERFLOW: "غير قابل للحساب: القيم المُدخلة تتجاوز نطاق الحساب العدديّ"
    " (WATER-NUMERIC-OVERFLOW) — ليست بيانات ناقصة؛ راجع وحدات القياس",
    REASON_CA_MG_ZERO: "غير قابل للحساب: Ca + Mg = صفر",
}


def _not_computable_class(index_ar: str, reason: str | None) -> dict | None:
    if reason is None:
        return None
    return {"class": None, "note_ar": f"{index_ar} {_NOT_COMPUTABLE_NOTE_AR[reason]}"}


# ─── درجات القيود على الاستعمال (FAO-29) ────────────────────────────────────
#
# المصدر: Ayers, R.S. & Westcot, D.W. (1985). Water Quality for Agriculture. FAO Irrigation
# and Drainage Paper 29 Rev. 1, Table 1 "Guidelines for interpretation of water quality for
# irrigation". القيم أدناه من الجدول المنشور؛ لم يُتَح جلبُ النصّ الأصليّ من بيئة البناء
# (fao.org غير مسموح في الشبكة) فنُقلت من الجدول كما يُستشهَد به، وكلّها في هذا الموضع وحده.
DEGREE_NONE = "none"
DEGREE_SLIGHT_TO_MODERATE = "slight_to_moderate"
DEGREE_SEVERE = "severe"

# الملوحة: ECw (dS/m) < 0.7 لا قيود · 0.7–3.0 طفيفة إلى متوسّطة · > 3.0 شديدة.
FAO29_SALINITY_ECW_DSM = (0.7, 3.0)

# النفاذيّة (يُقيَّم SAR وECw معاً): لكلّ صفّ SAR (من، إلى) عتبتا ECw (dS/m):
# ECw > none_above ⇒ لا قيود · none_above ≥ ECw ≥ severe_below ⇒ طفيفة إلى متوسّطة ·
# ECw < severe_below ⇒ شديدة. الماء الأقلّ ملوحةً عند SAR نفسه أسوأ نفاذيّةً.
# حدود الصفوف نصف مفتوحة [من، إلى) كاصطلاح ``classify_sar``؛ SAR ≥ 40 خارج مدى الجدول
# فيُقرأ بصفّه الأخير (الأشدّ) ويُعلَن ذلك.
FAO29_INFILTRATION_ROWS: tuple[tuple[float, float, float, float], ...] = (
    # (sar_from, sar_to, ecw_none_above, ecw_severe_below)
    (0.0, 3.0, 0.7, 0.2),
    (3.0, 6.0, 1.2, 0.3),
    (6.0, 12.0, 1.9, 0.5),
    (12.0, 20.0, 2.9, 1.3),
    (20.0, 40.0, 5.0, 2.9),
)

_DEGREE_RANK = {DEGREE_NONE: 0, DEGREE_SLIGHT_TO_MODERATE: 1, DEGREE_SEVERE: 2}
_DEGREE_AR = {
    DEGREE_NONE: "لا قيود",
    DEGREE_SLIGHT_TO_MODERATE: "قيود طفيفة إلى متوسّطة",
    DEGREE_SEVERE: "قيود شديدة",
}


def _infiltration_degree(
    sar: float, ec_dsm: float
) -> tuple[str, tuple[float, float, float, float]]:
    row = next((r for r in FAO29_INFILTRATION_ROWS if r[0] <= sar < r[1]), None)
    if row is None:
        row = FAO29_INFILTRATION_ROWS[-1]
    _, _, none_above, severe_below = row
    if ec_dsm > none_above:
        return DEGREE_NONE, row
    if ec_dsm < severe_below:
        return DEGREE_SEVERE, row
    return DEGREE_SLIGHT_TO_MODERATE, row


def classify_infiltration(sar: float | None, ec_dsm: float | None) -> dict:
    """خطر النفاذيّة (FAO-29 Table 1): درجة القيد من SAR مقروءاً مع ECw، لا من SAR وحده.

    ``sodium_attributable``: هل الصوديوم سببُ الدرجة؟ يُقارَن بصفّ SAR 0–3 عند ECw نفسها؛
    إن تساوت الدرجتان فالقيد ناتجٌ عن قلّة ملوحة الماء وحدها لا عن الصوديوم.
    """
    if sar is None or ec_dsm is None:
        return {"class": None, "note_ar": "النفاذيّة غير مقيّمة (تحتاج SAR وEC معاً)"}
    degree, row = _infiltration_degree(sar, ec_dsm)
    baseline, _ = _infiltration_degree(0.0, ec_dsm)
    sar_from, sar_to, none_above, severe_below = row
    out = {
        "class": degree,
        "degree": degree,
        "standard": "FAO-29 Table 1",
        "sar_row": f"{sar_from:g}-{sar_to:g}",
        "ecw_none_above_dsm": none_above,
        "ecw_severe_below_dsm": severe_below,
        "sodium_attributable": _DEGREE_RANK[degree] > _DEGREE_RANK[baseline],
        "restriction_ar": f"{_DEGREE_AR[degree]} (SAR {sar:g} مع ECw {ec_dsm:g} dS/m)",
    }
    if sar >= FAO29_INFILTRATION_ROWS[-1][1]:
        out["note_ar"] = "SAR خارج مدى جدول FAO-29 (≤40) — قُرئ بالصفّ الأشدّ"
    return out


def classify_ec(ec_dsm: float | None) -> dict:
    """تصنيف ملوحة ماء الريّ بالـEC (FAO-29)."""
    if ec_dsm is None:
        return {"class": None, "note_ar": "EC غير مقيس"}
    if not _finite_non_negative(ec_dsm):
        return {"class": None, "note_ar": "EC غير صالحة — لا تصنيف"}
    none_below, severe_above = FAO29_SALINITY_ECW_DSM
    if ec_dsm < none_below:
        return {
            "class": "low",
            "degree": DEGREE_NONE,
            "restriction_ar": "خطر الملوحة منخفض وفق EC فقط",
        }
    if ec_dsm <= severe_above:
        return {
            "class": "moderate",
            "degree": DEGREE_SLIGHT_TO_MODERATE,
            "restriction_ar": "قيود طفيفة إلى متوسّطة — راقب الملوحة وجزء الغسيل",
        }
    return {
        "class": "severe",
        "degree": DEGREE_SEVERE,
        "restriction_ar": "قيود شديدة — غسيل ملحي ضروري",
    }


def classify_rsc(rsc: float | None) -> dict:
    """تصنيف خطر القلويّة بالـRSC (USDA Bulletin 197)."""
    if rsc is None:
        return {"class": None, "note_ar": "RSC غير محسوب (نقص أيونات)"}
    if rsc < 1.25:
        return {"class": "safe", "hazard_ar": "آمن"}
    if rsc <= 2.50:
        return {"class": "marginal", "hazard_ar": "هامشي — إدارة ريّ جيّدة + مراقبة"}
    return {"class": "unsuitable", "hazard_ar": "غير مناسب — خطر قلويّة عالٍ، يحتاج جبس"}


def classify_sar(sar: float | None) -> dict:
    """تصنيف خطر الصوديوم (sodicity) بالـSAR (USSL)."""
    if sar is None:
        return {"class": None, "note_ar": "SAR غير محسوب (نقص أيونات)"}
    if sar < 10:
        return {"class": "low", "hazard_ar": "منخفض"}
    if sar < 18:
        return {"class": "medium", "hazard_ar": "متوسّط — مشاكل نفاذيّة محتملة بالطين"}
    if sar < 26:
        return {"class": "high", "hazard_ar": "مرتفع — خطر sodicity"}
    return {"class": "very_high", "hazard_ar": "مرتفع جدّاً — غير مناسب بلا معالجة"}


def analyze_water_sample(sample: WaterSample) -> dict:
    """يحلّل عيّنة ماء ريّ: يحسب SAR/RSC + يصنّف الملوحة/الصوديوم/القلويّة.

    صدق: يعتمد فقط القيم المُدخَلة؛ المؤشّر الذي يحتاج قيمة غائبة يُعلَن غير
    محسوب. لا تصنيف عامّ بلا بيانات كافية. يُعلِن البيانات الناقصة صراحةً.
    """
    # Validate first: a mutated instance must not reach arithmetic with an invalid value.
    errors = invalid_water_inputs(sample)
    if errors:
        raise ValueError("invalid water sample: " + ", ".join(errors))

    sar, sar_reason = sar_with_reason(sample.na, sample.ca, sample.mg)
    rsc, rsc_reason = rsc_with_reason(sample.co3, sample.hco3, sample.ca, sample.mg)

    missing: list[str] = []
    for fname in ("na", "ca", "mg", "hco3", "co3", "ec_dsm"):
        if getattr(sample, fname) is None:
            missing.append(fname)

    # خلاصة عامّة: أسوأ تصنيف يحكم (المبدأ المحافِظ)
    ec_c = classify_ec(sample.ec_dsm)
    rsc_c = _not_computable_class("RSC", rsc_reason) or classify_rsc(rsc)
    sar_c = _not_computable_class("SAR", sar_reason) or classify_sar(sar)
    # المؤشّر الذي لم يُحسَب رغم اكتمال مدخلاته يُعلَن بسببه (لا يُقرأ «بيانات ناقصة»).
    indices_not_computable = [
        {
            "index": index,
            "reason": reason,
            **({"code": WATER_NUMERIC_OVERFLOW} if reason == REASON_NUMERIC_OVERFLOW else {}),
        }
        for index, reason in (("sar", sar_reason), ("rsc_meq_l", rsc_reason))
        if reason is not None
    ]
    infil_c = classify_infiltration(sar, sample.ec_dsm if ec_c.get("class") else None)
    flags: list[str] = []
    if ec_c.get("class") == "severe":
        flags.append("ملوحة شديدة")
    if rsc_c.get("class") == "unsuitable":
        flags.append("قلويّة عالية")
    if sar_c.get("class") in ("high", "very_high"):
        flags.append("صوديوم مرتفع")
    if infil_c.get("class") == DEGREE_SEVERE:
        flags.append("خطر نفاذيّة شديد (SAR مع ECw)")

    # الدرجة الوسطى (FAO-29 «طفيفة إلى متوسّطة»): ليست «صالح» بلا قيد. كلّ مؤشّر يسمّي
    # درجته ومعياره. قيد النفاذيّة الطفيف الناتج عن قلّة الملوحة وحدها (SAR لا يغيّر
    # الدرجة عن صفّ 0–3) يُعلَن تنبيهاً لا قيداً: لو عُدّ قيداً لما بلغ أيُّ ماءٍ «لا قيود»،
    # فعتبة «لا قيود» للنفاذيّة (ECw > 0.7) لا تلتقي مع عتبة الملوحة (ECw < 0.7).
    restrictions: list[dict] = []
    advisories: list[str] = []
    if ec_c.get("class") is not None and ec_c["degree"] != DEGREE_NONE:
        restrictions.append(
            {
                "index": "ec_dsm",
                "axis": "salinity",
                "value": sample.ec_dsm,
                "degree": ec_c["degree"],
                "standard": "FAO-29 Table 1",
                "reason_ar": f"الملوحة: EC {sample.ec_dsm:g} dS/m — {_DEGREE_AR[ec_c['degree']]}",
            }
        )
    if infil_c.get("class") is not None and infil_c["degree"] != DEGREE_NONE:
        if infil_c["degree"] == DEGREE_SEVERE or infil_c["sodium_attributable"]:
            restrictions.append(
                {
                    "index": "sar",
                    "axis": "infiltration",
                    "value": sar,
                    "ec_dsm": sample.ec_dsm,
                    "degree": infil_c["degree"],
                    "standard": "FAO-29 Table 1",
                    "reason_ar": f"النفاذيّة: {infil_c['restriction_ar']}",
                }
            )
        else:
            advisories.append(
                "ماء منخفض الملوحة: قد يضعف ترشيح التربة السطحيّة"
                f" (FAO-29: {_DEGREE_AR[infil_c['degree']]} عند ECw {sample.ec_dsm:g})"
            )
    if rsc_c.get("class") in ("marginal", "unsuitable"):
        restrictions.append(
            {
                "index": "rsc_meq_l",
                "axis": "alkalinity",
                "value": rsc,
                "degree": (
                    DEGREE_SLIGHT_TO_MODERATE if rsc_c["class"] == "marginal" else DEGREE_SEVERE
                ),
                "standard": "Eaton 1950 / USDA (RSC)",
                "reason_ar": f"القلويّة: RSC {rsc:g} meq/L — {rsc_c['hazard_ar']}",
            }
        )
    restriction_flags_ar = [
        r["reason_ar"] for r in restrictions if r["degree"] == DEGREE_SLIGHT_TO_MODERATE
    ]

    # الحكم العامّ «صالح» يحتاج المحاور الثلاثة محسوبة (ملوحة EC، صوديوم SAR، قلويّة RSC).
    # خطرٌ مرصود في أيّ محور يكفي لحكم «يحتاج معالجة» ولو نقصت البقيّة؛ أمّا غياب الخطر
    # مع محورٍ غير محسوب فهو «بيانات غير كافية» لا «صالح» — والنتائج الجزئيّة تبقى ظاهرة.
    not_assessed = [
        axis
        for axis, cls in (("salinity", ec_c), ("sodicity", sar_c), ("alkalinity", rsc_c))
        if cls.get("class") is None
    ]
    if flags:
        verdict = "needs_treatment"
        suitable_ar = f"يحتاج معالجة: {'، '.join(flags)}"
    elif not_assessed:
        # قيدٌ متوسّط مرصود مع محورٍ غير محسوب لا يكفي لحكم «صالح مع قيود»: قد يكون المحور
        # الغائب شديداً. القيود المرصودة تبقى ظاهرة في ``restrictions``.
        verdict = "insufficient_data"
        suitable_ar = "بيانات غير كافية للحكم العامّ"
    elif restrictions:
        verdict = "suitable_with_restrictions"
        suitable_ar = f"صالح مع قيود وإدارة: {'، '.join(restriction_flags_ar)}"
    else:
        verdict = "suitable"
        suitable_ar = "صالح للريّ"

    return {
        "sample_id": sample.sample_id,
        "source": sample.source,
        "indices": {"sar": sar, "rsc_meq_l": rsc, "ec_dsm": sample.ec_dsm, "ph": sample.ph},
        "classification": {
            "salinity": ec_c,
            "alkalinity_rsc": rsc_c,
            "sodicity_sar": sar_c,
            "infiltration_fao29": infil_c,
        },
        "hazard_flags_ar": flags,
        "restrictions": restrictions,
        "restriction_flags_ar": restriction_flags_ar,
        "advisories_ar": advisories,
        "verdict": verdict,
        "not_assessed": not_assessed,
        "indices_not_computable": indices_not_computable,
        "suitable_ar": suitable_ar,
        "missing_inputs": missing,  # صدق: نُعلن ما لم يُقَس
        "data_complete": not missing and not not_assessed,
    }


# ─── جودة خليط المصادر (WELL-BLEND-WATER-QUALITY-NOT-COMPUTED-01) ─────────────
#
# الحقل يُروى من خليطٍ بنسبٍ حجميّة (`mixing_ratio`)، وجودةُ الخليط غيرُ جودة أيّ مصدر:
#
# - EC: متوسّطٌ مرجَّح بالحجم Σ fᵢ·ECᵢ. المزج الخطّيّ للتوصيليّة تقريبٌ مقبول زراعيّاً
#   (يُهمل ترسّب الأملاح وتأثيرات الأزواج الأيونيّة) — يُعلَن تقريباً لا قياساً.
# - SAR: **ليس خطّيّاً** في النسب. يُحسَب من تراكيز الخليط الأيونيّة (كلُّ أيونٍ مرجَّحٌ
#   بالحجم بـmeq/L) ثمّ SAR = Na / √((Ca+Mg)/2). متوسّطُ SAR المصادر المرجَّح جوابٌ مختلف
#   وخاطئ، فلا يُحسَب أبداً بديلاً؛ ونقصُ أيٍّ من Na/Ca/Mg ⇒ «غير محسوب» لا صفرٌ ولا تقدير.
#
# النسب: مصدرٌ وحيد بنسبةٍ غير معلنة (NULL) = المصدر كلّه (عقد v214: NULL = sole/undeclared).
# أكثر من مصدر ⇒ كلُّ نسبةٍ معلنةٌ، منتهيةٌ، ضمن [0, 1]، ومجموعُها 1 ضمن تفاوتٍ صغير
# (يُطبَّع ضمنه فقط)؛ وإلّا فالخليط غير محسوب — لا تطبيعَ يخترع نسباً لم تُعلَن.

BLEND_RATIO_SUM_TOLERANCE = 1e-3
BLEND_ION_FIELDS = ("sodium_meq_l", "calcium_meq_l", "magnesium_meq_l")

BLEND_COMPUTED = "computed"
BLEND_PARTIAL = "partial"
BLEND_NOT_COMPUTABLE = "not_computable"


def _finite_non_negative(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _not_computable(reason: str, **extra: object) -> dict:
    return {"status": BLEND_NOT_COMPUTABLE, "value": None, "reason": reason, **extra}


def _blend_fractions(components: list[dict]) -> tuple[list[float] | None, str | None]:
    """نسبُ المزج المُتحقَّق منها، أو (None, سبب). لا تطبيعَ إلّا ضمن التفاوت."""
    if not components:
        return None, "no_active_sources"
    ratios = [c.get("mixing_ratio") for c in components]
    if len(components) == 1 and ratios[0] is None:
        return [1.0], None  # مصدرٌ وحيد بلا نسبة معلنة = المصدر كلّه
    if any(r is None for r in ratios):
        return None, "mixing_ratio_undeclared"
    if any(not _finite_non_negative(r) or r > 1 for r in ratios):
        return None, "mixing_ratio_invalid"
    total = float(sum(ratios))
    if abs(total - 1.0) > BLEND_RATIO_SUM_TOLERANCE:
        return None, "mixing_ratios_do_not_sum_to_one"
    return [float(r) / total for r in ratios], None


def compute_blend_water_quality(components: list[dict]) -> dict:
    """EC وSAR لخليط مصادر ريّ من نسب المزج الحجميّة.

    ``components``: عنصرٌ لكلّ مصدر — ``source_id`` · ``mixing_ratio`` (0..1 أو None) ·
    ``ec_ds_m`` (dS/m) · ``sodium_meq_l``/``calcium_meq_l``/``magnesium_meq_l`` (meq/L، اختياريّة).
    مصدرٌ نسبتُه صفر لا يدخل الخليط فلا تُشترط بياناتُه.

    صدق: كلُّ مؤشّرٍ ينقصه مدخلٌ يُعاد ``not_computable`` بسببٍ مسمّى ومصادرَ ناقصة، و``value``
    فيه None — لا صفر ولا متوسّطُ SAR مرجَّح.
    """
    fractions, ratio_reason = _blend_fractions(components)
    if fractions is None:
        return {
            "status": BLEND_NOT_COMPUTABLE,
            "reason": ratio_reason,
            "fractions": [],
            "ec_ds_m": _not_computable(ratio_reason),
            "sar": _not_computable(ratio_reason),
            "ions_meq_l": None,
        }

    parts = [(c, f) for c, f in zip(components, fractions, strict=True) if f > 0]

    # EC: Σ fᵢ·ECᵢ (تقريبٌ خطّيّ مُعلَن)
    ec_missing = [str(c.get("source_id")) for c, _ in parts if c.get("ec_ds_m") is None]
    ec_invalid = [
        str(c.get("source_id"))
        for c, _ in parts
        if c.get("ec_ds_m") is not None and not _finite_non_negative(c.get("ec_ds_m"))
    ]
    if ec_invalid:
        ec = _not_computable("source_ec_invalid", source_ids=ec_invalid)
    elif ec_missing:
        ec = _not_computable("source_ec_missing", source_ids=ec_missing)
    else:
        ec_value = round(sum(f * float(c["ec_ds_m"]) for c, f in parts), 3)
        ec = (
            {
                "status": BLEND_COMPUTED,
                "value": ec_value,
                "method": "volume_weighted_linear_mixing_approximation",
            }
            if math.isfinite(ec_value)
            else _not_computable(REASON_NUMERIC_OVERFLOW, code=WATER_NUMERIC_OVERFLOW)
        )

    # SAR: من الأيونات المخلوطة لا من SAR المصادر
    ion_missing = [
        str(c.get("source_id")) for c, _ in parts if any(c.get(k) is None for k in BLEND_ION_FIELDS)
    ]
    ion_invalid = [
        str(c.get("source_id"))
        for c, _ in parts
        if any(
            c.get(k) is not None and not _finite_non_negative(c.get(k)) for k in BLEND_ION_FIELDS
        )
    ]
    ions: dict | None = None
    if ion_invalid:
        sar = _not_computable("source_ions_invalid", source_ids=ion_invalid)
    elif ion_missing:
        sar = _not_computable("source_ions_missing", source_ids=ion_missing)
    else:
        blended = {k: sum(f * float(c[k]) for c, f in parts) for k in BLEND_ION_FIELDS}
        if not all(math.isfinite(v) for v in blended.values()):
            value, reason = None, REASON_NUMERIC_OVERFLOW
        else:
            value, reason = sar_with_reason(
                blended["sodium_meq_l"], blended["calcium_meq_l"], blended["magnesium_meq_l"]
            )
        if value is None:
            # صدق: لا SAR = 0 ولا inf، وسببُ الفيض غيرُ سبب Ca+Mg = 0.
            sar = (
                _not_computable(reason, code=WATER_NUMERIC_OVERFLOW)
                if reason == REASON_NUMERIC_OVERFLOW
                else _not_computable(REASON_CA_MG_ZERO)
            )
        else:
            sar = {"status": BLEND_COMPUTED, "value": value, "method": "sar_from_blended_ions"}
            ions = {k: round(v, 4) for k, v in blended.items()}

    computed = [m["status"] == BLEND_COMPUTED for m in (ec, sar)]
    status = (
        BLEND_COMPUTED
        if all(computed)
        else BLEND_PARTIAL
        if any(computed)
        else BLEND_NOT_COMPUTABLE
    )
    return {
        "status": status,
        "reason": None,
        "fractions": [
            {"source_id": str(c.get("source_id")), "fraction": round(f, 6)}
            for c, f in zip(components, fractions, strict=True)
        ],
        "ec_ds_m": ec,
        "sar": sar,
        "ions_meq_l": ions,
    }
