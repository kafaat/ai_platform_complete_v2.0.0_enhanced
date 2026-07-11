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

from api.water_balance import KC_BY_CROP_STAGE

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

# مرادفات عربيّة → مفتاح إنجليزي
_CROP_ALIASES: dict[str, str] = {
    "قمح": "wheat",
    "شعير": "barley",
    "ذرة": "maize",
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
    key = crop.strip().lower()
    key = _CROP_ALIASES.get(crop.strip(), _CROP_ALIASES.get(key, key))
    return key, key in _CROP_PARAMS


def _params_for(crop_key: str) -> CropParams:
    return _CROP_PARAMS.get(crop_key, _GENERIC_PARAMS)


# ─── المدخلات والمخرجات ──────────────────────────────────────────


@dataclass
class DayWeather:
    """طقس يوم واحد للمحاكاة. الإشعاع/ET₀ اختياريّان (يُقدَّران عند الغياب)."""

    t_min_c: float
    t_max_c: float
    solar_mj_m2: float | None = None  # إشعاع كلّي MJ/m²/يوم
    et0_mm: float | None = None  # ET₀ مرجعي FAO-56 (mm/يوم)
    rain_mm: float = 0.0  # مطر اليوم (mm)


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


@dataclass
class SimResult:
    crop: str
    crop_recognized: bool
    days_simulated: int
    gdd_total: float
    gdd_to_maturity: float
    maturity_reached: bool
    lai_max: float
    biomass_kg_ha: float
    yield_kg_ha: float
    yield_low_kg_ha: float  # حدّ أدنى للنطاق (≈ −20٪)
    yield_high_kg_ha: float  # حدّ أعلى للنطاق (≈ +20٪)
    water_need_mm: float  # ETc الموسمي
    water_supply_mm: float | None  # مطر + ريّ إن عُرف
    water_stress_factor: float  # 0..1 (1 = بلا إجهاد)
    confidence: float  # 0..1
    rationale_ar: str
    # مصدر fAPAR المُستعمَل في حساب الإشعاع المُمتصّ:
    #   "modeled"  = الحدّ المُنمذَج (1 − e^(−k·LAI)) — السلوك الافتراضي.
    #   "observed" = fAPAR مرصود من القمر الصناعي (نموذج كفاءة الإنتاج RS).
    fapar_source: str = "modeled"
    assumptions_ar: list[str] = field(default_factory=list)
    warnings_ar: list[str] = field(default_factory=list)


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


def _seasonal_water_need(crop_key: str, et0_series: list[float | None]) -> float:
    """ETc الموسمي = Σ(ET₀_يوم × Kc_للمرحلة) موزّعاً على مراحل FAO-56.

    يوزّع أيّام الموسم على المراحل بالنِّسب القياسيّة ويضرب ET₀ بـKc المرحلة.
    WS-C.1b: يوم بلا ET0 (None — لا تقدير محلّيّ) يُتجاهَل في المجموع (لا يُلفَّق صفراً
    مُضلِّلاً ولا ET0 محلّيّاً)؛ النتيجة تقدير أدنى مع أيّام محسوبة أقلّ.
    """
    n = len(et0_series)
    if n == 0:
        return 0.0
    kc_map = KC_BY_CROP_STAGE.get(
        crop_key, {"initial": 0.4, "development": 0.8, "mid": 1.1, "late": 0.6}
    )
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
        clean = [float(v) for v in observed if _valid(v)]
        if not clean or len(clean) != len(observed):
            # سلسلة فارغة أو فيها قيم غير صالحة ⇒ نُهمل المرصود ونوسم البطلان.
            if not clean:
                return None, True
            had_invalid = len(clean) != len(observed)
            series = (clean + [clean[-1]] * n_days)[:n_days]
            return series, had_invalid
        series = (clean + [clean[-1]] * n_days)[:n_days]
        return series, False
    return None, True


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

    if not recognized:
        warnings.append(
            f"المحصول «{ctx.crop or 'غير محدّد'}» غير مُعرّف في قاعدة المعاملات — "
            "استُخدم نموذج عامّ (معاملات وسطيّة). عايِر ميدانيّاً."
        )

    weather = ctx.weather
    if not weather:
        warnings.append("لا توجد سلسلة طقس — تعذّرت المحاكاة الزمنيّة. النتيجة صفريّة/غير ذات دلالة.")
        return SimResult(
            crop=crop_key or (ctx.crop or ""),
            crop_recognized=recognized,
            days_simulated=0,
            gdd_total=0.0,
            gdd_to_maturity=p.gdd_to_maturity,
            maturity_reached=False,
            lai_max=0.0,
            biomass_kg_ha=0.0,
            yield_kg_ha=0.0,
            yield_low_kg_ha=0.0,
            yield_high_kg_ha=0.0,
            water_need_mm=0.0,
            water_supply_mm=None,
            water_stress_factor=1.0,
            confidence=0.0,
            rationale_ar="لا بيانات طقس كافية للمحاكاة — لا تقدير.",
            assumptions_ar=assumptions,
            warnings_ar=warnings,
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

    override = ctx.gdd_daily_override
    et0_override = ctx.et0_daily_override
    for day_idx, day in enumerate(weather):
        # WS-C.1c Zero-Legacy: نواة GDD من **محرّك الطقس** فقط (سلسلة محقونة) — لا gdd_day
        # محلّيّ. يوم بلا GDD محرّك ⇒ يُتجاهَل (fail-closed، لا يُلفَّق)؛ يُعلَن كقيد.
        if override is not None and day_idx < len(override) and override[day_idx] is not None:
            gdd_cum += float(override[day_idx])
        else:
            missing_gdd_days += 1
        lai = _lai_at(gdd_cum, p.gdd_to_maturity, p.lai_max)
        lai_peak = max(lai_peak, lai)

        solar = day.solar_mj_m2
        if solar is None:
            # تقدير حسب شهر اليوم (من تاريخ البذر + الإزاحة) — أدقّ من ثابت واحد.
            day_month = (
                (ctx.sowing_date + timedelta(days=day_idx)).month
                if ctx.sowing_date is not None
                else None
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
        if (
            et0_override is not None
            and day_idx < len(et0_override)
            and et0_override[day_idx] is not None
        ):
            et0 = float(et0_override[day_idx])
        else:
            et0 = day.et0_mm
        if et0 is None:
            missing_et0_days += 1  # يوم بلا ET0 (لا تقدير محلّيّ) — يُعلَن كقيد
        et0_series.append(et0)
        rain_total += max(0.0, day.rain_mm)

    days = len(weather)
    maturity_reached = gdd_cum >= p.gdd_to_maturity

    # g/m² → kg/ha  (1 g/m² = 10 kg/ha)
    biomass_kg_ha = biomass_g_m2 * 10.0

    # احتياج الماء الموسمي ETc (FAO-56) + مقارنة بالعرض (مطر + ريّ).
    water_need = _seasonal_water_need(crop_key, et0_series)
    water_supply: float | None = None
    if ctx.irrigation_mm_total is not None or rain_total > 0:
        water_supply = rain_total + (ctx.irrigation_mm_total or 0.0)

    # معامل إجهاد مائي: يخفض الإنتاج عند العجز، لا يضخّمه فوق ١.
    if water_supply is not None and water_need > 0:
        ratio = water_supply / water_need
        water_stress = max(0.4, min(1.0, ratio))
        if ratio < 0.7:
            warnings.append(
                f"عجز مائي: العرض ({water_supply:.0f} مم) أقلّ من الاحتياج ({water_need:.0f} مم) — "
                "الإنتاج المُقدَّر مخفوض بعامل إجهاد."
            )
    else:
        water_stress = 1.0
        if ctx.irrigation_mm_total is None:
            assumptions.append("لم يُعرَف الريّ الموسمي — افتُرض ريّ كافٍ (بلا إجهاد مائي).")

    yield_potential = biomass_kg_ha * p.harvest_index
    yield_kg_ha = yield_potential * water_stress

    # نطاق عدم اليقين الصريح (±20٪) — لا رقم قاطع.
    yield_low = yield_kg_ha * (1.0 - _UNCERTAINTY_FRAC)
    yield_high = yield_kg_ha * (1.0 + _UNCERTAINTY_FRAC)

    # افتراضات حول التواريخ/التغطية.
    if ctx.sowing_date is None:
        assumptions.append("لم يُعرَف تاريخ البذار — اعتُمدت سلسلة الطقس المُمرَّرة كما هي.")
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
    if not maturity_reached:
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
    confidence = round(min(0.85, confidence), 2)  # سقف ٨٥٪ — لا يقين كامل بلا قياس ميداني

    rationale = (
        f"محاكاة {days} يوم: GDD={gdd_cum:.0f}/{p.gdd_to_maturity:.0f} °C·day، "
        f"أقصى LAI≈{lai_peak:.2f}، كتلة حيويّة≈{biomass_kg_ha:.0f} kg/ha، "
        f"الإنتاج المُقدَّر≈{yield_kg_ha:.0f} kg/ha (نطاق {yield_low:.0f}–{yield_high:.0f}، "
        f"HI={p.harvest_index:.2f})، احتياج الماء≈{water_need:.0f} mm. "
        f"الثقة {confidence:.0%} — تقدير نموذجي (RUE/FAO-56)، عايِر ميدانيّاً."
    )

    return SimResult(
        crop=crop_key or (ctx.crop or ""),
        crop_recognized=recognized,
        days_simulated=days,
        gdd_total=round(gdd_cum, 1),
        gdd_to_maturity=p.gdd_to_maturity,
        maturity_reached=maturity_reached,
        lai_max=round(lai_peak, 2),
        biomass_kg_ha=round(biomass_kg_ha, 1),
        yield_kg_ha=round(yield_kg_ha, 1),
        yield_low_kg_ha=round(yield_low, 1),
        yield_high_kg_ha=round(yield_high, 1),
        water_need_mm=round(water_need, 1),
        water_supply_mm=round(water_supply, 1) if water_supply is not None else None,
        water_stress_factor=round(water_stress, 3),
        confidence=confidence,
        rationale_ar=rationale,
        fapar_source=fapar_source,
        assumptions_ar=assumptions,
        warnings_ar=warnings,
    )
