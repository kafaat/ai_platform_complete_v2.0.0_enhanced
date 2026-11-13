"""
api/season_simulation.py — محاكاة موسم محصوليّة صرفة (RUE / FAO-56).

ماذا يفعل (نموذج خفيف، نقيّ، بلا تبعيّات ثقيلة):
  ١. تراكم GDD (Growing Degree Days) من سلسلة حرارة يوميّة (طريقة المتوسّط مع
     قصّ عند درجة الأساس t_base وسقف t_cap لكلّ محصول).
  ٢. الكتلة الحيويّة فوق الأرض عبر RUE (Monteith 1977): الكتلة = RUE × الإشعاع
     المُمتصّ المتراكم. الإشعاع المُمتصّ = PAR × fAPAR، حيث fAPAR إمّا **مُنمذَج**
     من LAI عبر Beer-Lambert (1 − e^(−k·LAI))، وإمّا **مرصود** من القمر الصناعي
     (نموذج كفاءة الإنتاج RS — Monteith 1972/1977، Running et al. MOD17) إن مُرِّر.
  ٣. مؤشّر LAI كمنحنى نموّ منطقيّ مع GDD (يصعد ثمّ يهبط حول النضج) — مؤشّر، لا
     قياس. أقصى LAI يُقيَّد بسقف المحصول.
  ٤. الإنتاج = الكتلة الحيويّة × مؤشّر الحصاد HI (Harvest Index).
  ٥. احتياج الماء الموسمي ETc = Σ(ET₀ × Kc) عبر مراحل النموّ (FAO-56).
  ٦. تحجيم نهائيّ بمعامل إجهاد مائيّ (إن توفّر مطر/ري موسمي مقابل ETc) — يخفض
     الإنتاج تحت العجز المائي، ولا يضخّمه فوق الإمكان.

⚠ صدق علمي حاسم (لا يقين مُلفَّق):
  • هذه **تقديرات نموذجيّة**، لا قياسات. المعاملات (RUE, HI, t_base, GDD المستهدف،
    أقصى LAI) إرشاديّة من أدبيّات FAO/Monteith، تحتاج معايرة يمنيّة محلّيّة.
  • نُرجع **نطاقاً** (yield_low/yield_high ≈ ±20٪) لا رقماً قاطعاً، ودرجة ثقة،
    وقائمة افتراضات/تحذيرات صريحة (محصول غير مُعرّف، طقس مُقدَّر، مراحل ناقصة).
  • عند نقص المدخلات نتدهور برشاقة (افتراضات موسومة) بدل الرفض أو التلفيق.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from api.water_balance import kc_map_for_crop

ENGINE_NAME = "rue-fao56"
ENGINE_VERSION = "rue-fao56/1"
PARAMETER_VERSION = "sahool-season-defaults/1"

# ─── معرفة المحاصيل (معاملات نموذجيّة إرشاديّة) ───────────────────
# المصادر: FAO-56 (Kc, طول المراحل)، Monteith 1977 / Sinclair & Muchow 1999
# (RUE نموذجيّ ~1.2–1.7 g/MJ للحبوب C3، ~1.7–2.0 لـC4)، HI من أدبيّات الإنتاج.
# ⚠ كلّها UNVALIDATED DEFAULTS — تحتاج معايرة يمنيّة قبل الاعتماد في قرار حقيقي.


@dataclass(frozen=True)
class CropParams:
    t_base_c: float  # درجة أساس GDD (تحتها لا نموّ)
    t_cap_c: float  # سقف GDD (فوقه لا فائدة حراريّة إضافيّة)
    gdd_to_maturity: float  # GDD التراكمي المتوقّع للنضج (°C·day)
    rue_g_per_mj: float  # كفاءة استخدام الإشعاع (g biomass / MJ PAR)
    harvest_index: float  # نسبة الحبّ/الثمرة من الكتلة الحيويّة الكلّيّة
    lai_max: float  # أقصى مؤشّر مساحة ورقيّة نموذجيّ
    k_extinction: float  # معامل انطفاء الضوء (Beer-Lambert) ~0.5–0.7


# ملاحظة: الأسماء بالعربيّة والإنجليزيّة معاً (الواجهة قد ترسل أيّاً منهما).
_CROP_PARAMS: dict[str, CropParams] = {
    "wheat": CropParams(0.0, 30.0, 1800.0, 1.40, 0.42, 5.5, 0.55),
    "barley": CropParams(0.0, 30.0, 1600.0, 1.35, 0.45, 5.0, 0.55),
    "maize": CropParams(8.0, 34.0, 1500.0, 1.70, 0.50, 5.0, 0.55),
    "sorghum": CropParams(8.0, 34.0, 1700.0, 1.55, 0.40, 4.5, 0.55),
    "millet": CropParams(10.0, 34.0, 1400.0, 1.45, 0.35, 4.0, 0.55),
    "potato": CropParams(2.0, 30.0, 1600.0, 1.30, 0.75, 4.5, 0.55),
    "tomato": CropParams(7.0, 32.0, 1800.0, 1.30, 0.55, 4.0, 0.60),
    "onion": CropParams(4.0, 30.0, 1700.0, 1.20, 0.55, 3.0, 0.50),
    "alfalfa": CropParams(5.0, 32.0, 900.0, 1.50, 0.50, 5.0, 0.60),
}

# مرادفات عربيّة → مفتاح إنجليزي (احتياط محلّيّ؛ المحلِّل المشترك resolve_crop_id أوّلاً).
# «ذرة» مفردةً = sorghum (القرار الموحَّد في core/season_phenology.py) — كانت هنا maize.
_CROP_ALIASES: dict[str, str] = {
    "قمح": "wheat",
    "شعير": "barley",
    "ذرة": "sorghum",
    "ذرة شامية": "maize",
    "ذرة رفيعة": "sorghum",
    "دخن": "millet",
    "بطاطس": "potato",
    "بطاطا": "potato",
    "طماطم": "tomato",
    "بندورة": "tomato",
    "بصل": "onion",
    "برسيم": "alfalfa",
}

# نموذج عامّ آمن حين يكون المحصول غير مُعرّف — موسوم بصراحة في النتيجة.
_GENERIC_PARAMS = CropParams(5.0, 32.0, 1700.0, 1.35, 0.45, 4.5, 0.55)

# نسبة الإشعاع الكلّي القابل للامتصاص ضوئيّاً (PAR ≈ 48٪ من الإشعاع الكلّي).
_PAR_FRACTION = 0.48
# إشعاع كلّي يوميّ افتراضي للهضبة اليمنيّة حين يغيب القياس (MJ/m²/يوم) — تقدير.
# متوسّط سنويّ احتياطيّ يُستعمَل فقط حين يتعذّر معرفة الشهر (لا تاريخ بذر).
_DEFAULT_SOLAR_MJ = 21.0
# تقدير الإشعاع الكلّي اليوميّ حسب الشهر لليمن (~15°N، إشعاع عالٍ) — MJ/m²/يوم.
# يُستعمَل حين يغيب القياس لكنّ الشهر معروف (أدقّ من ثابت موسميّ واحد).
_YEMEN_SOLAR_BY_MONTH = {
    1: 18.0,
    2: 20.0,
    3: 22.0,
    4: 24.0,
    5: 25.0,
    6: 26.0,
    7: 24.0,
    8: 23.0,
    9: 22.0,
    10: 20.0,
    11: 18.0,
    12: 17.0,
}


def _solar_estimate(month: int | None) -> float:
    """تقدير الإشعاع اليوميّ حين يغيب القياس: حسب الشهر إن عُرف، وإلّا المتوسّط السنويّ."""
    if month is None:
        return _DEFAULT_SOLAR_MJ
    return _YEMEN_SOLAR_BY_MONTH.get(month, _DEFAULT_SOLAR_MJ)


# نطاق عدم اليقين حول التقدير المركزي (±) — يُعبَّر عنه كنطاق صريح لا رقم قاطع.
_UNCERTAINTY_FRAC = 0.20

# طول المراحل النسبيّ (FAO-56 مبسّط) لتوزيع ETc حين تغيب مراحل المستخدم.
_STAGE_FRACTIONS = (
    ("initial", 0.20),
    ("development", 0.30),
    ("mid", 0.30),
    ("late", 0.20),
)


def normalize_crop(crop: str | None) -> tuple[str, bool]:
    """يُرجع (مفتاح المحصول، هل هو مُعرّف). يطبّع العربيّة والحالة."""
    if not crop:
        return "", False
    from core.season_phenology import resolve_crop_id

    shared = resolve_crop_id(crop)
    if shared in _CROP_PARAMS:
        return shared, True
    key = crop.strip().lower()
    key = _CROP_ALIASES.get(crop.strip(), _CROP_ALIASES.get(key, key))
    return key, key in _CROP_PARAMS


def _params_for(crop_key: str) -> CropParams:
    return _CROP_PARAMS.get(crop_key, _GENERIC_PARAMS)


# ─── المدخلات والمخرجات ──────────────────────────────────────────


@dataclass
class DayWeather:
    """طقس يوم واحد للمحاكاة. الإشعاع/ET₀ اختياريّان (يُقدَّران عند الغياب)."""

    # الحرارتان تقبلان الغياب: تصلان من أرشيف ERA5 (متأخّرٌ ~٥ أيّام) `None` لا `0°م`،
    # ومحرّكُ الطقس يُرجِع لليوم الناقص GDD/ET0 `None` فيُعَدّ ويُعلَن قيداً هنا — لا يُحسَب
    # من `(0, 0)` صامتاً (TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01).
    t_min_c: float | None
    t_max_c: float | None
    solar_mj_m2: float | None = None  # إشعاع كلّي MJ/m²/يوم
    et0_mm: float | None = None  # ET₀ مرجعي FAO-56 (mm/يوم)
    rain_mm: float | None = 0.0  # المطر المرصود (mm)، None = بيانات مفقودة لا صفر


@dataclass
class SimContext:
    """سياق محاكاة الموسم (يُجمَّع في النواة من القاعدة + الطقس)."""

    crop: str | None
    sowing_date: date | None = None
    season_end: date | None = None
    weather: list[DayWeather] = field(default_factory=list)
    irrigation_mm_total: float | None = None  # ريّ موسمي مُطبَّق (mm) إن عُرف
    # fAPAR مرصود من القمر الصناعي (0..1): إمّا متوسّط موسمي (scalar) أو سلسلة
    # يوميّة (list بطول أيّام الموسم). حين يتوفّر ويكون صالحاً يحلّ محلّ fAPAR
    # المُنمذَج من LAI (نموذج كفاءة الإنتاج RS). غيابه/بطلانه ⇒ السلوك الحالي.
    observed_fapar: float | list[float] | None = None
    # WS-C.1c: سلسلة GDD يوميّة محقونة من **محرّك الطقس** (المصدر الكنسيّ). حين تتوفّر
    # تُستخدم بدل نواة gdd_day المحلّيّة (المصفوفة يوماً بيوم). قيمة None ليوم ⇒ عودة
    # لـgdd_day لذلك اليوم. غياب السلسلة كلّها ⇒ السلوك المحلّيّ الحاليّ تماماً.
    gdd_daily_override: list[float | None] | None = None
    # WS-C.1b: سلسلة ET0 يوميّة محقونة من محرّك الطقس (المصدر الكنسيّ). None لكامل
    # السلسلة ⇒ يُستعمَل et0 المُمرَّر مع اليوم؛ لا Hargreaves محلّيّ في أيّ حال.
    et0_daily_override: list[float | None] | None = None
    # أوّل يوم في سلسلة الطقس. None ⇒ النافذة تبدأ يوم البذار (عقد المسار). مع تاريخ البذار
    # يُشتقّ منه عمر المحصول لكلّ يوم ⇒ Kc يوميّ من منحنى البطاقة لا توزيع تناسبيّ.
    window_start: date | None = None
    irrigation_type: str | None = None  # rainfed must not imply assured irrigation


@dataclass
class SimResult:
    crop: str
    crop_recognized: bool
    days_simulated: int
    gdd_total: float | None
    gdd_to_maturity: float
    maturity_reached: bool | None
    lai_max: float | None
    biomass_kg_ha: float | None
    # None حين يكون المحصول غير مُعرّف: لا HI/RUE خاصّ به ⇒ لا غلّة تُختلَق من معاملات عامّة.
    yield_kg_ha: float | None
    yield_low_kg_ha: float | None  # حدّ أدنى للنطاق (≈ −20٪)
    yield_high_kg_ha: float | None  # حدّ أعلى للنطاق (≈ +20٪)
    water_need_mm: float | None  # None حين ينقص ET0؛ ليس 0 mm
    water_supply_mm: float | None  # مطر + ريّ إن عُرف
    water_stress_factor: float | None  # None إذا تعذّر تقييم الإجهاد
    confidence: float  # 0..1
    rationale_ar: str
    # مصدر fAPAR المُستعمَل في حساب الإشعاع المُمتصّ:
    #   "modeled"  = الحدّ المُنمذَج (1 − e^(−k·LAI)) — السلوك الافتراضي.
    #   "observed" = fAPAR مرصود من القمر الصناعي (نموذج كفاءة الإنتاج RS).
    fapar_source: str = "modeled"
    assumptions_ar: list[str] = field(default_factory=list)
    warnings_ar: list[str] = field(default_factory=list)
    # "estimated" | "unavailable_unrecognized_crop" — حالة الغلّة صراحةً لا رقم عامّ.
    yield_status: str = "estimated"
    limitations: list[str] = field(default_factory=list)


# ─── دوالّ النموذج النقيّة ────────────────────────────────────────


def crop_gdd_policy(crop: str | None) -> tuple[float, float]:
    """سياسة GDD للمحصول (الأساس، السقف) — °م. لغير المُعرَّف: معاملات وسطيّة.

    يُصدّرها الراوتر ليطلب نواة GDD من محرّك الطقس بنفس عتبات هذا النموذج
    (method="modified") — فيبقى التفويض مُحافِظاً على الطريقة والسياسة.
    """
    crop_key, _ = normalize_crop(crop)
    p = _params_for(crop_key)
    return p.t_base_c, p.t_cap_c


# WS-C.1c Zero-Legacy: نواة GDD اليوميّة (gdd_day، طريقة Baskerville–Emin المبسّطة =
# method="modified") أُزيلت — مِلك محرّك الطقس (services/weather-service/gdd.py). المحاكاة
# تستهلك السلسلة المحقونة (SimContext.gdd_daily_override)؛ crop_gdd_policy أدناه يبقى (سياسة
# العتبات) ليطلب الراوتر نواة المحرّك بنفس الأساس/السقف.


def _lai_at(gdd_cum: float, gdd_mat: float, lai_max: float) -> float:
    """مؤشّر LAI من نسبة تقدّم GDD — يصعد ثمّ يتراجع حول النضج (منحنى جرسي).

    قمّة LAI قرب ~70٪ من الطريق للنضج ثمّ شيخوخة. مؤشّر تقريبي لا قياس.
    """
    if gdd_mat <= 0:
        return 0.0
    p = gdd_cum / gdd_mat
    if p <= 0:
        return 0.0
    # منحنى: صعود لوجستي حتّى ~0.7 ثمّ هبوط خطّي نحو النضج.
    if p <= 0.7:
        growth = 1.0 - math.exp(-3.5 * (p / 0.7))
        return lai_max * growth
    # شيخوخة بعد القمّة: من lai_max نزولاً إلى ~0.25·lai_max عند النضج.
    decline = max(0.0, 1.0 - 0.75 * ((p - 0.7) / 0.3))
    return lai_max * decline


def _absorbed_par(solar_mj: float, lai: float, k: float) -> float:
    """الإشعاع المُمتصّ ضوئيّاً (MJ PAR/m²) = PAR × (1 − e^(−k·LAI)) — Beer-Lambert.

    الحدّ (1 − e^(−k·LAI)) هو fAPAR **المُنمذَج** من LAI. حين يتوفّر fAPAR مرصود
    من القمر الصناعي يُستبدل هذا الحدّ بـ_absorbed_par_observed (نفس بنية المعادلة).
    """
    par = solar_mj * _PAR_FRACTION
    fraction_intercepted = 1.0 - math.exp(-k * max(0.0, lai))
    return par * fraction_intercepted


def _absorbed_par_observed(solar_mj: float, fapar: float) -> float:
    """الإشعاع المُمتصّ من fAPAR **مرصود** (MJ PAR/m²) = PAR × fAPAR.

    نموذج كفاءة الإنتاج (RS production-efficiency, Monteith 1972/1977؛
    Running et al. MOD17): يحلّ fAPAR المُقاس من القمر الصناعي محلّ الحدّ
    المُنمذَج (1 − e^(−k·LAI))، ويبقى RUE/HI كما هما (افتراضات الأدبيّات نفسها).
    """
    par = solar_mj * _PAR_FRACTION
    return par * min(1.0, max(0.0, fapar))


def fapar_from_ndvi(ndvi: float) -> float:
    """تحويل NDVI → fAPAR بالعلاقة الخطّيّة المنشورة المُستشهَد بها.

    fAPAR ≈ 1.24·NDVI − 0.168  (Myneni & Williams, 1994, "On the relationship
    between FAPAR and NDVI", Remote Sensing of Environment 49(3):200–211)،
    مقصوصة إلى [0, 1]. **لا ثابت مُختلق** — نفس المعادلة المستعملة في
    services/raster-service لحساب طبقة fAPAR من NDVI.
    """
    return min(1.0, max(0.0, 1.24 * ndvi - 0.168))


def _per_day_kc_series(crop_key: str, n: int, days_since_sowing_start: int) -> list[float] | None:
    """Kc يوميّ من منحنى FAO-56 لبطاقة المحصول بحسب **عمر المحصول الفعليّ** — أو None بلا بطاقة.

    اليوم ``i`` من النافذة عمره ``days_since_sowing_start + i`` يوماً منذ البذار، فتشغيلٌ في
    منتصف الموسم يأخذ Kc مرحلته الحقيقيّة لا مرحلةً من توزيعٍ تناسبيّ على طول النافذة.
    القصّ مطابق لـ ``season_phenology.stage_kc`` (قبل البذار ⇒ Kc_ini، بعد الدورة ⇒ Kc_end)؛
    البروفايل يُبنى مرّة واحدة لا لكلّ يوم.
    """
    from core.engines.fao56 import kc_for_age
    from core.season_phenology import crop_kc_profile, resolve_crop_id

    profile = crop_kc_profile(resolve_crop_id(crop_key))
    if profile is None:
        return None
    total = profile.total_season_days
    return [
        kc_for_age(profile, min(max(0, days_since_sowing_start + i), total))[0] for i in range(n)
    ]


def _seasonal_water_need(
    crop_key: str,
    et0_series: list[float | None],
    days_since_sowing_start: int | None = None,
) -> float:
    """ETc الموسمي = Σ(ET₀_يوم × Kc_يوم) (FAO-56).

    حين يُعرَف عمر المحصول في أوّل يوم من النافذة (``days_since_sowing_start``) وللمحصول
    بطاقة: Kc يوميّ من منحنى البطاقة بحسب عمر كلّ يوم. وإلّا (لا بذار/لا بطاقة) يوزّع أيّام
    النافذة على المراحل بالنِّسب القياسيّة — تقدير خشن موسوم في الافتراضات.
    WS-C.1b: يوم بلا ET0 (None — لا تقدير محلّيّ) يُتجاهَل في المجموع (لا يُلفَّق صفراً
    مُضلِّلاً ولا ET0 محلّيّاً)؛ النتيجة تقدير أدنى مع أيّام محسوبة أقلّ.
    """
    n = len(et0_series)
    if n == 0:
        return 0.0
    if days_since_sowing_start is not None:
        daily_kc = _per_day_kc_series(crop_key, n, days_since_sowing_start)
        if daily_kc is not None:
            return sum(e * kc for e, kc in zip(et0_series, daily_kc, strict=True) if e is not None)
    kc_map, _ = kc_map_for_crop(crop_key)  # بطاقة المحصول — المصدر الوحيد لـKc
    total = 0.0
    idx = 0
    for stage, frac in _STAGE_FRACTIONS:
        count = max(1, round(n * frac)) if stage != "late" else (n - idx)
        kc = kc_map.get(stage, kc_map.get("mid", 1.0))
        for _ in range(count):
            if idx >= n:
                break
            if et0_series[idx] is not None:
                total += et0_series[idx] * kc
            idx += 1
    # أي بقايا (تقريب) بمعامل المرحلة الأخيرة (تجاهُل None — لا اختلاق)
    while idx < n:
        if et0_series[idx] is not None:
            total += et0_series[idx] * kc_map.get("late", 0.6)
        idx += 1
    return total


def _resolve_observed_fapar(
    observed: float | list[float] | None, n_days: int
) -> tuple[list[float] | None, bool]:
    """يحوّل observed_fapar (scalar/سلسلة/None) إلى سلسلة يوميّة بطول n_days.

    يُرجع (سلسلة fAPAR لكلّ يوم أو None إن لا مرصود صالح، هل وُجد مُدخل غير صالح).
    القيم الصالحة في [0, 1]. السلسلة تُقصّ/تُمدَّد (بآخر قيمة) لمطابقة عدد الأيّام.
    scalar ⇒ يُكرَّر لكلّ يوم. None أو قيم خارج [0,1] ⇒ تجاهُل (السلوك المُنمذَج).
    """

    def _valid(v: object) -> bool:
        return isinstance(v, int | float) and not isinstance(v, bool) and 0.0 <= v <= 1.0

    if observed is None:
        return None, False
    if isinstance(observed, int | float) and not isinstance(observed, bool):
        if not _valid(observed):
            return None, True
        return [float(observed)] * n_days, False
    if isinstance(observed, list):
        # Invalid entries must never be filtered out: removal would shift
        # subsequent observations to earlier dates and corrupt daily APAR.
        if not observed or not all(_valid(value) for value in observed):
            return None, True
        clean = [float(value) for value in observed]
        series = (clean + [clean[-1]] * n_days)[:n_days]
        return series, False
    return None, True


def _finite_nonnegative(value: object) -> float | None:
    """Keep observed zero distinct from absent/invalid weather or irrigation evidence."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if math.isfinite(v) and v >= 0 else None


def simulate_season(ctx: SimContext) -> SimResult:
    """يحاكي موسماً (RUE/FAO-56) ويُرجع SimResult بتقديرات + نطاق + ثقة.

    نقيّ بالكامل (لا قاعدة/شبكة). يتدهور برشاقة عند نقص المدخلات بافتراضات
    موسومة. لا يُرجع رقماً قاطعاً — يعرض نطاقاً وثقةً وافتراضات صريحة.

    **متغيّر كفاءة الإنتاج (RS production-efficiency, Monteith 1972/1977؛
    Running et al. MOD17):** حين يُمرَّر ``ctx.observed_fapar`` صالحاً (متوسّط
    موسمي scalar أو سلسلة يوميّة، كلّ قيمة في [0,1])، يُستبدل الحدّ المُنمذَج
    fAPAR = (1 − e^(−k·LAI)) بالـfAPAR **المرصود** من القمر الصناعي في حساب
    الإشعاع المُمتصّ اليوميّ (APAR = PAR × fAPAR_مرصود)، فيقود الضوءُ المُقاس
    الكتلةَ الحيويّة عبر **نفس** RUE والإنتاجَ عبر **نفس** HI الموجودَين أصلاً.
    لا ثوابت زراعيّة جديدة: RUE/HI/k تبقى افتراضات الأدبيّات نفسها (UNVALIDATED
    DEFAULTS — تحتاج معايرة يمنيّة ميدانيّة، نفس التحذير الصادق). عند غياب/بطلان
    المرصود يعود السلوك مطابقاً تماماً للنسخة الحاليّة (fapar_source="modeled").
    """
    crop_key, recognized = normalize_crop(ctx.crop)
    p = _params_for(crop_key)
    assumptions: list[str] = []
    warnings: list[str] = []

    limitations: list[str] = []
    yield_status = "estimated"
    if not recognized:
        warnings.append(
            f"المحصول «{ctx.crop or 'غير محدّد'}» غير مُعرّف في قاعدة المعاملات — "
            "استُخدم نموذج عامّ (معاملات وسطيّة) للتراكم الحراريّ والماء فقط؛ "
            "لا تقدير غلّة بلا مؤشّر حصاد خاصّ بالمحصول."
        )
        limitations.append("UNRECOGNIZED_CROP_NO_YIELD_ESTIMATE")
        yield_status = "unavailable_unrecognized_crop"

    weather = ctx.weather
    if not weather:
        warnings.append("لا توجد سلسلة طقس — لا يمكن حساب غلة أو احتياج ماء أو نضج.")
        return SimResult(
            crop=crop_key or (ctx.crop or ""),
            crop_recognized=recognized,
            days_simulated=0,
            gdd_total=None,
            gdd_to_maturity=p.gdd_to_maturity,
            maturity_reached=None,
            lai_max=None,
            biomass_kg_ha=None,
            yield_kg_ha=None,
            yield_low_kg_ha=None,
            yield_high_kg_ha=None,
            water_need_mm=None,
            water_supply_mm=None,
            water_stress_factor=None,
            confidence=0.0,
            rationale_ar="لا بيانات طقس كافية للمحاكاة — لا تقدير.",
            assumptions_ar=assumptions,
            warnings_ar=warnings,
            yield_status="unavailable_no_weather" if recognized else yield_status,
            limitations=[*limitations, "WEATHER_SERIES_MISSING"],
        )

    # fAPAR مرصود (إن مُرِّر) → سلسلة يوميّة. None ⇒ نُبقي الحدّ المُنمذَج (1−e^…).
    fapar_series, fapar_invalid = _resolve_observed_fapar(ctx.observed_fapar, len(weather))
    use_observed = fapar_series is not None
    fapar_source = "observed" if use_observed else "modeled"
    if fapar_invalid:
        warnings.append(
            "fAPAR المرصود المُمرَّر غير صالح (خارج [0,1] أو سلسلة فارغة) — "
            "تجاهُلٌ والعودة إلى fAPAR المُنمذَج من LAI."
        )

    # تراكم GDD + الكتلة الحيويّة (RUE) + متابعة أقصى LAI يوماً بيوم.
    gdd_cum = 0.0
    biomass_g_m2 = 0.0
    lai_peak = 0.0
    et0_series: list[float | None] = []
    rain_total = 0.0
    estimated_solar_days = 0
    missing_et0_days = 0
    missing_gdd_days = 0
    missing_rain_days = 0

    override = ctx.gdd_daily_override
    et0_override = ctx.et0_daily_override
    for day_idx, day in enumerate(weather):
        # WS-C.1c Zero-Legacy: نواة GDD من **محرّك الطقس** فقط (سلسلة محقونة) — لا gdd_day
        # محلّيّ. يوم بلا GDD محرّك ⇒ يُتجاهَل (fail-closed، لا يُلفَّق)؛ يُعلَن كقيد.
        gdd_value = (
            _finite_nonnegative(override[day_idx])
            if override is not None and day_idx < len(override)
            else None
        )
        if gdd_value is None:
            missing_gdd_days += 1
        else:
            gdd_cum += gdd_value
        lai = _lai_at(gdd_cum, p.gdd_to_maturity, p.lai_max)
        lai_peak = max(lai_peak, lai)

        solar = _finite_nonnegative(day.solar_mj_m2)
        if solar is None:
            # تقدير حسب شهر اليوم (من تاريخ البذر + الإزاحة) — أدقّ من ثابت واحد.
            day_start = ctx.window_start or ctx.sowing_date
            day_month = (
                (day_start + timedelta(days=day_idx)).month if day_start is not None else None
            )
            solar = _solar_estimate(day_month)
            estimated_solar_days += 1
        if use_observed:
            # نموذج كفاءة الإنتاج RS: APAR = PAR × fAPAR_مرصود (بدل الحدّ المُنمذَج).
            apar = _absorbed_par_observed(solar, fapar_series[day_idx])
        else:
            apar = _absorbed_par(solar, lai, p.k_extinction)
        # RUE: g/MJ × MJ/m² ⇒ g/m² من الكتلة الحيويّة اليوميّة (نفس RUE في الحالتين).
        biomass_g_m2 += p.rue_g_per_mj * apar

        # WS-C.1b: ET0 من محرّك الطقس (سلسلة محقونة) — المصدر الوحيد؛ **لا Hargreaves
        # محلّيّ**. أولويّة: السلسلة المحقونة الكنسيّة، ثمّ et0 المُمرَّر مع اليوم. غياب
        # كليهما ⇒ None (يوم بلا ET0 — يُتجاهَل في احتياج الماء، لا يُلفَّق).
        # An explicit canonical None is authoritative absence. Do NOT silently
        # substitute an older ERA5 ET0 value behind the owner-produced series.
        if et0_override is not None:
            raw_et0 = et0_override[day_idx] if day_idx < len(et0_override) else None
        else:
            raw_et0 = day.et0_mm
        et0 = _finite_nonnegative(raw_et0)
        if et0 is None:
            missing_et0_days += 1
        et0_series.append(et0)
        rain = _finite_nonnegative(day.rain_mm)
        if rain is None:
            missing_rain_days += 1
        else:
            rain_total += rain

    days = len(weather)
    days_since_sowing_start = (
        ((ctx.window_start or ctx.sowing_date) - ctx.sowing_date).days
        if ctx.sowing_date is not None
        else None
    )
    maturity_reached = gdd_cum >= p.gdd_to_maturity

    # g/m² → kg/ha  (1 g/m² = 10 kg/ha)
    biomass_kg_ha = biomass_g_m2 * 10.0

    # احتياج الماء الموسمي ETc (FAO-56) + مقارنة بالعرض (مطر + ريّ).
    water_need_partial = _seasonal_water_need(crop_key, et0_series, days_since_sowing_start)
    water_need = water_need_partial if missing_et0_days == 0 else None
    irrigation_total = _finite_nonnegative(ctx.irrigation_mm_total)
    if ctx.irrigation_mm_total is not None and irrigation_total is None:
        limitations.append("IRRIGATION_TOTAL_INVALID")
    water_supply: float | None = None
    rainfed = (ctx.irrigation_type or "").strip().lower() == "rainfed"
    if missing_rain_days == 0 and (irrigation_total is not None or rain_total > 0 or rainfed):
        # For a rainfed season, observed zero rain is a known zero supply, not an
        # absence of irrigation information that would justify assuming a watered crop.
        water_supply = rain_total + (irrigation_total or 0.0)

    # Do not invent a stress factor when weather coverage is incomplete.
    if water_need is None or missing_rain_days or "IRRIGATION_TOTAL_INVALID" in limitations:
        water_stress: float | None = None
    elif water_supply is not None and water_need > 0:
        ratio = water_supply / water_need
        water_stress = max(0.4, min(1.0, ratio))
        if ratio < 0.7:
            warnings.append(
                f"عجز مائي: العرض ({water_supply:.0f} مم) أقلّ من الاحتياج ({water_need:.0f} مم) — "
                "الإنتاج المُقدَّر مخفوض بعامل إجهاد."
            )
    else:
        water_stress = 1.0
        if irrigation_total is None:
            assumptions.append("لم يُعرَف الريّ الموسمي — افتُرض ريّ كافٍ (بلا إجهاد مائي).")

    # No quantitative yield from an incomplete canonical weather series.
    if missing_gdd_days:
        limitations.append("GDD_SERIES_INCOMPLETE")
    if missing_et0_days:
        limitations.append("ET0_SERIES_INCOMPLETE")
    if missing_rain_days:
        limitations.append("PRECIPITATION_SERIES_INCOMPLETE")
    if recognized and missing_gdd_days:
        yield_status = "unavailable_missing_gdd"
    elif recognized and missing_et0_days:
        yield_status = "unavailable_missing_et0"
    elif recognized and missing_rain_days:
        yield_status = "unavailable_missing_precipitation"
    elif recognized and "IRRIGATION_TOTAL_INVALID" in limitations:
        yield_status = "unavailable_invalid_irrigation"
    elif recognized and rainfed and yield_status == "estimated":
        # Documented rain is the only modelled supply; initial soil water is not.
        yield_status = "estimated_water_unverified"
    yield_available = (
        recognized
        and yield_status in ("estimated", "estimated_water_unverified")
        and water_stress is not None
    )
    yield_kg_ha = biomass_kg_ha * p.harvest_index * water_stress if yield_available else None
    yield_low = yield_kg_ha * (1.0 - _UNCERTAINTY_FRAC) if yield_kg_ha is not None else None
    yield_high = yield_kg_ha * (1.0 + _UNCERTAINTY_FRAC) if yield_kg_ha is not None else None

    # افتراضات حول التواريخ/التغطية.
    if ctx.sowing_date is None:
        assumptions.append(
            "لم يُعرَف تاريخ البذار — اعتُمدت سلسلة الطقس المُمرَّرة كما هي، ووُزِّع Kc على "
            "مراحل FAO-56 تناسبيّاً مع طول النافذة (لا عمر محصول معروف)."
        )
    if estimated_solar_days > 0:
        assumptions.append(
            f"الإشعاع الشمسي غير متوفّر لـ{estimated_solar_days} يوم — استُخدم تقدير "
            f"{_DEFAULT_SOLAR_MJ:.0f} MJ/m²/يوم (الهضبة اليمنيّة)."
        )
    if missing_et0_days > 0:
        assumptions.append(
            f"ET₀ غير متوفّر من محرّك الطقس لـ{missing_et0_days} يوم — استُبعِدت تلك الأيّام "
            "من احتياج الماء (لا تقدير Hargreaves محلّيّ داخل المنصّة)."
        )
    if missing_gdd_days > 0:
        assumptions.append(
            f"GDD غير متوفّر من محرّك الطقس لـ{missing_gdd_days} يوم — لم تُضَف تلك الأيّام "
            "للتراكم الحراريّ (لا نواة GDD محلّيّة داخل المنصّة)."
        )
    if missing_rain_days > 0:
        assumptions.append(
            f"بيانات المطر مفقودة أو غير صالحة لـ{missing_rain_days} يوم — "
            "لم تُحسب كصفر، وتعذّر إثبات العرض المائي."
        )
    if rainfed:
        assumptions.append(
            "الموسم مطريّ — استُخدم المطر الموثّق فقط في العرض المائي؛ "
            "الماء المخزون مبدئيّاً في التربة غير ممثّل في هذا النموذج."
        )
        limitations.append("RAINFED_INITIAL_SOIL_WATER_UNMODELED")
    if missing_gdd_days == 0 and not maturity_reached:
        warnings.append(
            f"لم يبلغ GDD التراكمي ({gdd_cum:.0f}) عتبة النضج ({p.gdd_to_maturity:.0f}) — "
            "التقدير لموسم غير مكتمل أو نافذة طقس أقصر من الدورة."
        )
    if use_observed:
        assumptions.append(
            "استُعمل fAPAR **مرصود** من القمر الصناعي بدل المُنمذَج (نموذج كفاءة "
            "الإنتاج RS — Monteith/MOD17). RUE/HI تبقى افتراضات الأدبيّات نفسها — "
            "عايِر ميدانيّاً."
        )

    # الثقة: تبدأ منخفضة، ترتفع بتعرّف المحصول + توفّر الطقس الحقيقي + اكتمال الموسم.
    confidence = 0.35
    if recognized:
        confidence += 0.20
    if estimated_solar_days == 0:
        confidence += 0.10
    if missing_et0_days == 0:
        confidence += 0.10
    if maturity_reached:
        confidence += 0.10
    if water_supply is not None:
        confidence += 0.05
    confidence = round(min(0.85, confidence), 2) if yield_available else 0.0
    if yield_status == "estimated_water_unverified":
        confidence = min(confidence, 0.45)

    yield_text = (
        f"الإنتاج المُقدَّر≈{yield_kg_ha:.0f} kg/ha (نطاق {yield_low:.0f}–{yield_high:.0f}، "
        f"HI={p.harvest_index:.2f})"
        if yield_kg_ha is not None
        else f"الإنتاج غير متاح ({yield_status}) — مدخلات أساسية مفقودة أو غير مؤهلة"
    )
    gdd_text = f"{gdd_cum:.0f}" if missing_gdd_days == 0 else "غير مكتمل"
    water_text = f"{water_need:.0f}" if water_need is not None else "غير متاح"
    biomass_text = f"{biomass_kg_ha:.0f}" if missing_gdd_days == 0 else "غير متاح"
    lai_text = f"{lai_peak:.2f}" if missing_gdd_days == 0 else "غير متاح"
    rationale = (
        f"محاكاة {days} يوم: GDD={gdd_text}/{p.gdd_to_maturity:.0f} °C·day، "
        f"أقصى LAI={lai_text}، "
        f"كتلة حيويّة≈{biomass_text} kg/ha، "
        f"{yield_text}، احتياج الماء≈{water_text} mm. "
        f"الثقة {confidence:.0%} — تقدير نموذجي (RUE/FAO-56)، عايِر ميدانيّاً."
    )

    return SimResult(
        crop=crop_key or (ctx.crop or ""),
        crop_recognized=recognized,
        days_simulated=days,
        gdd_total=round(gdd_cum, 1) if missing_gdd_days == 0 else None,
        gdd_to_maturity=p.gdd_to_maturity,
        maturity_reached=maturity_reached if missing_gdd_days == 0 else None,
        lai_max=round(lai_peak, 2) if missing_gdd_days == 0 else None,
        biomass_kg_ha=round(biomass_kg_ha, 1) if missing_gdd_days == 0 else None,
        yield_kg_ha=round(yield_kg_ha, 1) if yield_kg_ha is not None else None,
        yield_low_kg_ha=round(yield_low, 1) if yield_low is not None else None,
        yield_high_kg_ha=round(yield_high, 1) if yield_high is not None else None,
        water_need_mm=round(water_need, 1) if water_need is not None else None,
        water_supply_mm=round(water_supply, 1) if water_supply is not None else None,
        water_stress_factor=round(water_stress, 3) if water_stress is not None else None,
        confidence=confidence,
        rationale_ar=rationale,
        fapar_source=fapar_source,
        assumptions_ar=assumptions,
        warnings_ar=warnings,
        yield_status=yield_status,
        limitations=limitations,
    )


# ─── نافذة المحاكاة (من البذار إلى نهاية الموسم) ───────────────────────────────────────
# سقف صلب لطول النافذة (يوم): دورة سنويّة واحدة على الأكثر — حدّ لحجم طلب الطقس التاريخيّ.
_SIM_HARD_MAX_WINDOW_DAYS = 366
# أرشيف ERA5 التاريخيّ يتأخّر ~5 أيّام — لا يُطلَب أحدث من ذلك.
_ERA5_LAG_DAYS = 5


class SimWindowError(ValueError):
    """نافذة لا تُحاكى (لا تاريخ بذار / قصيرة / في المستقبل) — رسالتها عربيّة للمستخدم (422)."""

    def __init__(self, detail_ar: str):
        super().__init__(detail_ar)
        self.detail_ar = detail_ar


@dataclass(frozen=True)
class SimWindow:
    """نافذة المحاكاة المخطَّطة — بما طُلِب وما سيُحاكى، فلا قصّ صامت."""

    start: date
    end: date
    cap_days: int
    days_requested: int  # أيّام النافذة المطلوبة (البذار → نهاية الموسم أو اليوم)، شاملة
    days_simulated: int  # أيّام النافذة المحاكاة فعلاً (بعد السقف وتأخّر ERA5)، شاملة
    truncated: bool  # True ⇔ قُصَّت النافذة لأنّها أطول من السقف

    def limitations(self) -> list[str]:
        return ["SIM_WINDOW_TRUNCATED"] if self.truncated else []

    def warnings_ar(self) -> list[str]:
        if not self.truncated:
            return []
        return [
            f"نافذة الموسم ({self.days_requested} يوم) أطول من سقف المحاكاة ({self.cap_days} "
            f"يوم) — حوكِيَ أوّل {self.days_simulated} يوم فقط من البذار حتّى "
            f"{self.end.isoformat()}؛ النتيجة لا تغطّي بقيّة الموسم."
        ]


def crop_cycle_window_cap(crop: str | None, floor_days: int) -> int:
    """سقف نافذة المحاكاة: طول دورة المحصول (بطاقته/معايرة المنطقة) أو ``floor_days`` أيّهما أطول.

    لا يقصر عن السقف التاريخيّ (``floor_days``) لأنّ مراحل البطاقة اسميّة (FAO-56) والنضج
    هنا يُقاس بـGDD (أبطأ في المرتفعات)، ويمتدّ لمحاصيل الدورة الطويلة بدل قصّها صامتاً.
    محدود بسقف صلب (سنة واحدة).
    """
    from core.season_phenology import crop_kc_profile, resolve_crop_id

    from api.crop_cycle import cycle_days_to_maturity

    crop_id = resolve_crop_id(crop)
    cycles = [floor_days]
    profile = crop_kc_profile(crop_id)
    if profile is not None:
        cycles.append(int(profile.total_season_days))
    region_cycle = cycle_days_to_maturity(crop_id)
    if region_cycle is not None:
        cycles.append(int(region_cycle))
    return min(max(cycles), _SIM_HARD_MAX_WINDOW_DAYS)


def plan_simulation_window(
    crop: str | None,
    sowing_date: date | None,
    season_end: date | None,
    today: date,
    *,
    floor_days: int,
) -> SimWindow:
    """يخطّط نافذة المحاكاة من البذار إلى نهاية الموسم (أو اليوم) — نقيّة.

    بلا تاريخ بذار ⇒ ``SimWindowError``: لا يُخترَع بدءٌ (كان اليوم−160) فيُحسَب عمر المحصول
    ومراحل Kc من بذارٍ وهميّ. نافذة أطول من السقف تُقصّ **معلَنةً** (``truncated``).
    """
    if sowing_date is None:
        raise SimWindowError(
            "الموسم بلا تاريخ بذار — لا يمكن معرفة عمر المحصول ومراحل نموّه، فلا تُشغَّل "
            "المحاكاة على بداية مُفترَضة. أضِف تاريخ البذار ثمّ أعِد المحاولة."
        )
    cap = crop_cycle_window_cap(crop, floor_days)
    start = sowing_date
    if season_end is not None and season_end < sowing_date:
        raise SimWindowError("تاريخ نهاية الموسم يسبق تاريخ البذار — صحّح تاريخَي الموسم.")
    requested_end = min(season_end, today) if season_end is not None else today
    if requested_end <= start:
        requested_end = min(start + timedelta(days=cap), today)
    win_end = requested_end
    truncated = False
    if (win_end - start).days > cap:
        win_end = start + timedelta(days=cap)
        truncated = True
    win_end = min(win_end, today - timedelta(days=_ERA5_LAG_DAYS))
    if win_end <= start:
        raise SimWindowError(
            "نافذة الموسم قصيرة جدّاً أو في المستقبل — لا بيانات طقس تاريخيّة كافية للمحاكاة."
        )
    return SimWindow(
        start=start,
        end=win_end,
        cap_days=cap,
        days_requested=max(0, (requested_end - start).days) + 1,
        days_simulated=(win_end - start).days + 1,
        truncated=truncated,
    )


# ─── ربط السجلّ التاريخيّ تلقائيّاً (حقل + يوم بذار + المحصول نفسه) ─────────────────────
#: أعمدة مساعدة يجلبها استعلام المرشّحين للمقارنة فقط — تُزال قبل أن يدخل السجلّ حزمة الإدخال.
AUTO_LINK_CROP_COLUMNS = ("link_crop_registry_ref", "link_variety_name")


def historical_record_crop_matches(
    season_crop: str | None, record_crop_ref: str | None, record_variety: str | None
) -> bool:
    """هل محصول السجلّ التاريخيّ هو محصول الموسم نفسه؟ بالمحلِّل القانونيّ على الطرفين.

    طرف السجلّ: ``crop_registry_ref`` و``variety_name`` يُحلّان معاً؛ ما يُحلّ منهما يجب أن
    يتّفق على crop_id واحد. أيّ طرف لا يُحلّ، أو تعارض، ⇒ False (لا ربط بالتخمين).
    """
    from core.season_phenology import resolve_crop_id

    mine = resolve_crop_id(season_crop)
    if mine is None:
        return False
    theirs = {resolve_crop_id(v) for v in (record_crop_ref, record_variety) if v}
    theirs.discard(None)
    return theirs == {mine}


def select_auto_link_candidate(candidates, season_crop: str | None) -> dict | None:
    """يختار السجلّ الوحيد المطابق محصولاً من مرشّحي (الحقل + يوم البذار) — أو None.

    صفر أو أكثر من مطابق ⇒ None (لا ربط). المُرجَع بلا الأعمدة المساعدة، فلا تتغيّر
    بصمة حزمة الإدخال بسبب المقارنة.
    """
    matching = [
        dict(c)
        for c in candidates
        if historical_record_crop_matches(
            season_crop, c[AUTO_LINK_CROP_COLUMNS[0]], c[AUTO_LINK_CROP_COLUMNS[1]]
        )
    ]
    if len(matching) != 1:
        return None
    return {k: v for k, v in matching[0].items() if k not in AUTO_LINK_CROP_COLUMNS}
