"""
sahool_core.engines.fao56
==========================
FAO-56 crop water requirement engine.

Computes irrigation requirement in the CORRECT methodological order
(established over the design discussion + verified against FAO sources):

    1. ET0   (reference ET — from WEATHER, the daily VARIABLE)
    2. Kc    (crop coefficient — from CROP + AGE, the biological CONSTANT)
    3. ETc   = ET0 * Kc            (standard crop ET)
    4. Ks    (stress: salinity + soil-water depletion)
    5. ETc_adj = ETc * Ks
    6. Net irrigation = ETc_adj - effective_rainfall
    7. Gross irrigation = (net + leaching_requirement) / irrigation_efficiency

KEY DISTINCTION (decided during design):
    ET0 = the VARIABLE   (changes daily/hourly with weather)
    Kc  = the CONSTANT    (biological fingerprint of the crop, by growth stage)

NO HARDCODED YIELD/COST NUMBERS. Pure FAO-56 physics — needs no training data.

Sources (cite explicitly per the critique's requirement):
  - Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998).
    "Crop evapotranspiration - Guidelines for computing crop water
    requirements." FAO Irrigation and Drainage Paper 56. FAO, Rome.
    https://www.fao.org/3/x0490e/x0490e00.htm
  - Penman-Monteith reference equation: FAO-56 Chapter 2, Eq. 6.
  - Kc by 4 growth stages: FAO-56 Chapter 6, Table 11/12.
  - Salinity stress (Ks): FAO-56 Chapter 8, yield-salinity relationship.
  - Leaching requirement: FAO-56 Chapter 8, Eq. 82.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# المصدر الموحّد لـET0 (H4): نواة Penman-Monteith واحدة (لا نُعيد كتابة الصيغة هنا).
from core.engines.et0 import penman_monteith_et0 as _pm_core


# ── Growth stages (FAO-56 Ch.6) ──────────────────────────────────────
class GrowthStage(str, Enum):
    INITIAL = "initial"  # planting -> ~10% ground cover
    DEVELOPMENT = "development"  # 10% cover -> effective full cover
    MID_SEASON = "mid_season"  # full cover -> start of maturity
    LATE_SEASON = "late_season"  # maturity -> harvest


@dataclass
class WeatherDay:
    """Daily weather inputs for ET0. All from weather-service."""

    temp_max_c: float
    temp_min_c: float
    humidity_pct: float  # mean relative humidity
    wind_speed_m_s: float  # at 2m height
    solar_radiation_mj_m2: float  # MJ/m2/day
    latitude_deg: float
    elevation_m: float
    day_of_year: int

    @property
    def temp_mean_c(self) -> float:
        return (self.temp_max_c + self.temp_min_c) / 2.0

    @property
    def diurnal_range_c(self) -> float:
        """DTR — diurnal temperature range. Large DTR in arid highlands is a
        real advantage (quality crops, lower night ET). Discussed in design."""
        return self.temp_max_c - self.temp_min_c


@dataclass
class CropKcProfile:
    """The CONSTANT — biological water fingerprint of a crop.
    Loaded from YAML crop card. Values per FAO-56 Table 11/12.
    """

    crop_id: str
    kc_initial: float
    kc_mid: float
    kc_end: float
    # stage lengths in days [initial, development, mid, late]
    stage_days: list[int]
    salt_tolerance_ece: float  # EC threshold dS/m (FAO-56 Table 23)
    salt_slope_pct: float  # % yield loss per dS/m above threshold
    source: str = "FAO-56 Table 11/12/23"

    @property
    def total_season_days(self) -> int:
        return sum(self.stage_days)


# ── ET0: Penman-Monteith (FAO-56 Eq. 6) ──────────────────────────────
def penman_monteith_et0(w: WeatherDay) -> float:
    """Reference evapotranspiration (mm/day) via FAO-56 Penman-Monteith.

    Delegates to the unified core (`core.engines.et0`) — behaviour preserved.
    `WeatherDay.temp_mean_c` = (max+min)/2, passed explicitly.
    """
    return _pm_core(
        w.temp_max_c,
        w.temp_min_c,
        w.temp_mean_c,
        w.solar_radiation_mj_m2,
        w.humidity_pct,
        w.wind_speed_m_s,
        w.latitude_deg,
        w.elevation_m,
        w.day_of_year,
    )


# ── Kc by age (FAO-56 Ch.6) ──────────────────────────────────────────
def kc_for_age(profile: CropKcProfile, days_after_planting: int) -> tuple[float, GrowthStage]:
    """Return (Kc, stage) for the crop's age. The CONSTANT side of the eq.

    Kc curve (FAO-56 Fig.34):
      initial:     flat kc_initial
      development: linear ramp kc_initial -> kc_mid
      mid_season:  flat kc_mid
      late_season: linear ramp kc_mid -> kc_end
    """
    d = days_after_planting
    s_ini, s_dev, s_mid, s_late = profile.stage_days
    if d <= s_ini:
        return profile.kc_initial, GrowthStage.INITIAL
    if d <= s_ini + s_dev:
        frac = (d - s_ini) / max(1, s_dev)
        kc = profile.kc_initial + frac * (profile.kc_mid - profile.kc_initial)
        return kc, GrowthStage.DEVELOPMENT
    if d <= s_ini + s_dev + s_mid:
        return profile.kc_mid, GrowthStage.MID_SEASON
    # late season
    frac = (d - s_ini - s_dev - s_mid) / max(1, s_late)
    frac = min(1.0, frac)
    kc = profile.kc_mid + frac * (profile.kc_end - profile.kc_mid)
    return kc, GrowthStage.LATE_SEASON


# ── Salinity stress Ks (FAO-56 Ch.8) ─────────────────────────────────
def salinity_stress_ks(profile: CropKcProfile, soil_ece: float) -> float:
    """Yield/ET reduction factor from soil salinity.
    FAO-56 Eq. 81 (Maas-Hoffman): linear above threshold.
    Returns Ks in [0, 1]. 1.0 = no stress.
    """
    if soil_ece <= profile.salt_tolerance_ece:
        return 1.0
    loss_pct = profile.salt_slope_pct * (soil_ece - profile.salt_tolerance_ece)
    return max(0.0, 1.0 - loss_pct / 100.0)


# ─────────────────────────────────────────────────────────────────────
# معامل المحصول المزدوج (Dual Crop Coefficient) — FAO-56 الفصل 7
# ─────────────────────────────────────────────────────────────────────
# المسار المفرد أعلاه (Kc واحد) يدمج النتح + التبخّر السطحيّ في معامل واحد.
# في الظروف الجافّة/التربة العارية/المراحل المبكّرة (وهي القاعدة في اليمن)،
# يكون التبخّر السطحيّ مكوّناً رئيساً لا ثانويّاً. النهج المزدوج يفصلهما:
#
#     ETc = (Kcb · Ks + Ke) · ET0                       (FAO-56 Eq. 80)
#
#   Kcb = معامل المحصول الأساسيّ (النتح فقط، تربة سطحيّة جافّة)
#   Ke  = معامل تبخّر التربة (يرتفع بعد الرّيّ/المطر، ينهار مع جفاف السطح)
#   Ks  = إجهاد مائيّ/ملحيّ يُخفّض الأساس (لا يُخفّض Ke — التبخّر فيزيائيّ)
#
# هذا المسار **إضافيّ واختياريّ**: المسار المفرد (compute_irrigation) يبقى
# الافتراضيّ وغير متغيّر. استخدم compute_etc_dual عند توفّر بيانات التربة السطحيّة.
#
# مراجع المعادلات (Allen et al. 1998, Ch.7):
#   Eq. 71  Ke = min( Kr·(Kc_max − Kcb) , few·Kc_max )
#   Eq. 72  Kc_max = max( {1.2 + [0.04(u2−2) − 0.004(RHmin−45)]·(h/3)^0.3} , Kcb+0.05 )
#   Eq. 73  TEW = 1000·(θFC − 0.5·θWP)·Ze
#   Eq. 74  Kr = (TEW − De) / (TEW − REW)   لـDe>REW ، وإلّا Kr=1
#   Eq. 75  few = min(1−fc , fw)
#   Eq. 80  ETc = (Kcb·Ks + Ke)·ET0


# جداول REW/TEW الافتراضيّة حسب القوام (FAO-56 Table 19, Ze=0.10–0.15م).
# REW = الماء المتبخّر بسهولة (المرحلة الأولى)، TEW = إجماليّ الماء المتبخّر.
# قيم تقريبيّة لعمق تبخّر Ze=0.10م — تُستخدم حين تغيب قياسات التربة السطحيّة.
# (mm) — مصدر: FAO-56 Table 19 / مثال الفصل 7.
_TEW_REW_BY_TEXTURE: dict[str, tuple[float, float]] = {
    # texture: (TEW_mm, REW_mm)  لعمق Ze=0.10م
    "sand": (8.0, 3.0),
    "sandy": (8.0, 3.0),
    "loamy sand": (10.0, 4.0),
    "sandy loam": (12.0, 6.0),
    "loam": (16.0, 8.0),
    "silt loam": (20.0, 9.0),
    "silt": (22.0, 10.0),
    "clay loam": (20.0, 10.0),
    "silty clay": (21.0, 11.0),
    "clay": (18.0, 12.0),
    "mixed": (16.0, 8.0),
}


def tew_rew_for_texture(texture: str) -> tuple[float, float]:
    """يُرجِع (TEW, REW) بالملّيمتر لقوام تربة، من جدول FAO-56 الافتراضيّ.

    ⚠️ افتراض صريح: حين تغيب قياسات التربة السطحيّة (θFC/θWP/Ze)، نستخدم قيم
    جدول FAO-56 Table 19 لعمق تبخّر Ze=0.10م. هذه تقديرات نوعيّة لا قياسات
    موقعيّة — تُحدَّد دقّتها بدقّة تصنيف القوام. القوام المجهول ⇐ "loam".
    """
    return _TEW_REW_BY_TEXTURE.get(texture.strip().lower(), _TEW_REW_BY_TEXTURE["loam"])


def kc_max(kcb: float, wind_speed_m_s: float, rh_min_pct: float, crop_height_m: float) -> float:
    """الحدّ الأعلى لمعامل المحصول بعد الرّيّ/المطر (FAO-56 Eq. 72).

    Kc_max = max( 1.2 + [0.04(u2−2) − 0.004(RHmin−45)]·(h/3)^0.3 , Kcb+0.05 )

    يُمثّل الطاقة المتاحة للتبخّر+النتح من سطح مبلّل. u2 = سرعة الرياح عند 2م،
    RHmin = أدنى رطوبة نسبيّة (%)، h = ارتفاع المحصول (م). القيم تُقصّ للنطاق
    الموصى به في FAO-56 (1.0 ≤ u2 ≤ 6، 20% ≤ RHmin ≤ 80%).
    """
    u2 = min(6.0, max(1.0, wind_speed_m_s))
    rh = min(80.0, max(20.0, rh_min_pct))
    h = max(0.05, crop_height_m)
    adj = 1.2 + (0.04 * (u2 - 2.0) - 0.004 * (rh - 45.0)) * (h / 3.0) ** 0.3
    return max(adj, kcb + 0.05)


def evaporation_reduction_kr(de_mm: float, tew_mm: float, rew_mm: float) -> float:
    """معامل تخفيض التبخّر Kr (FAO-56 Eq. 74) من موازنة ماء الطبقة السطحيّة.

    المرحلة 1 (طاقة-محدودة): De ≤ REW ⇒ Kr = 1 (تبخّر بالحدّ الأعلى).
    المرحلة 2 (انتشار-محدودة): De > REW ⇒ Kr = (TEW − De)/(TEW − REW).
    De = استنزاف الطبقة السطحيّة (mm)، يرتفع بالتبخّر وينخفض بالرّيّ/المطر.
    يُرجِع Kr في [0, 1].
    """
    if de_mm <= rew_mm:
        return 1.0
    denom = tew_mm - rew_mm
    if denom <= 0:
        return 0.0
    return max(0.0, min(1.0, (tew_mm - de_mm) / denom))


def few_exposed_wetted(fc: float, fw: float) -> float:
    """الكسر المعرّض-والمبلّل من سطح التربة few (FAO-56 Eq. 75).

    few = min(1 − fc , fw)
    fc = كسر الغطاء النباتيّ (الظلّ)، fw = كسر السطح المبلّل بالرّيّ.
    رّيّ بالتنقيط ⇒ fw صغير (~0.3)، رّيّ سطحيّ/مطر ⇒ fw≈1.
    التبخّر يحدث فقط من الجزء المكشوف وغير المظلَّل والمبلّل.
    """
    return max(0.0, min(1.0 - max(0.0, min(1.0, fc)), max(0.0, min(1.0, fw))))


def kcb_for_age(
    profile: CropKcProfile, days_after_planting: int, kcb_offset: float = 0.05
) -> tuple[float, GrowthStage]:
    """معامل المحصول الأساسيّ Kcb (النتح فقط) من منحنى Kc القائم.

    ⚠️ افتراض صريح: بطاقات SAHOOL تحمل Kc واحداً (مدمج) لا Kcb منفصلاً. نشتقّ
    Kcb بإزاحة ثابتة أسفل Kc (FAO-56: Kcb ≈ Kc − [0.05..0.10] في المراحل
    النشطة، إذ الفارق هو متوسّط مكوّن التبخّر السطحيّ). الإزاحة الافتراضيّة 0.05.
    هذا تقريب: القيمة الدقيقة تتطلّب بطاقة Kcb مُعايَرة (Table 17) غير متوفّرة.
    Kcb لا ينزل دون 0.15 (تربة عارية ⇒ نتح شبه معدوم في المرحلة الأوليّة).
    """
    kc, stage = kc_for_age(profile, days_after_planting)
    kcb = max(0.15, kc - kcb_offset)
    return kcb, stage


# ─── Kcb ديناميكيّ من الأقمار (NDVI) — FAO-56 §9.4 «Kc من كسر الغطاء» ──────────
# بدل اشتقاق Kcb من عمر المحصول (منحنى جدوليّ)، نشتقّه من **غطاء نباتيّ مرصود**
# (NDVI من raster-service): كسر الغطاء fc → معامل الكثافة Kd (Eq. 76) → Kcb = Kcb_full·Kd.
# هذا يربط محرّك المياه بالقمر: حقل متأخّر/مُجهَد يُظهِر NDVI أدنى ⇒ Kcb أدنى ⇒ احتياج أصدق.
# صدق: الحدود (NDVI_bare/NDVI_full) و ML تقديريّة **تحتاج معايرة محلّيّة** — تُعلَن صراحةً.


def fractional_cover_from_ndvi(
    ndvi: float, ndvi_bare: float = 0.15, ndvi_full: float = 0.85
) -> float:
    """كسر الغطاء النباتيّ fc من NDVI (تقدير خطّيّ مقصوص إلى [0, 1]).

    ``fc = (NDVI − NDVI_bare) / (NDVI_full − NDVI_bare)`` (علاقة fc–NDVI الشائعة).
    ⚠️ ``NDVI_bare``/``NDVI_full`` افتراضيّان (تربة عارية/غطاء كامل) **يحتاجان معايرة
    محلّيّة** لكلّ محصول/تربة. يرفع ``ValueError`` إن لم يكن ``NDVI_full > NDVI_bare``.
    """
    denom = ndvi_full - ndvi_bare
    if denom <= 0:
        raise ValueError("NDVI_full يجب أن يفوق NDVI_bare")
    return max(0.0, min(1.0, (ndvi - ndvi_bare) / denom))


def density_coefficient_kd(fc: float, crop_height_m: float, ml: float = 2.0) -> float:
    """معامل الكثافة Kd (FAO-56 Eq. 76): ``min(1, ML·fc, fc^(1/(1+h)))``.

    ``fc`` كسر الغطاء، ``h`` ارتفاع النبات (m)، ``ML`` مضاعِف الغطاء الفعّال (1.5–2.0).
    يصف انتقال Kcb من تربة عارية (fc=0 ⇒ Kd=0) إلى غطاء كامل (fc=1 ⇒ Kd=1). مقصوص [0,1].
    """
    fc = max(0.0, min(1.0, fc))
    if fc <= 0.0:
        return 0.0
    h = max(0.05, crop_height_m)
    return max(0.0, min(1.0, min(ml * fc, fc ** (1.0 / (1.0 + h)))))


def kcb_from_ndvi(
    ndvi: float,
    kcb_full: float,
    crop_height_m: float,
    *,
    ndvi_bare: float = 0.15,
    ndvi_full: float = 0.85,
    ml: float = 2.0,
) -> tuple[float, float]:
    """Kcb من NDVI عبر كسر الغطاء + معامل الكثافة (FAO-56 §9.4، Eq. 76-77).

    يُرجِع ``(kcb, fc)``: ``Kcb = Kcb_full · Kd(fc(NDVI), h)``. ``Kcb_full`` = Kcb عند الغطاء
    الكامل (ذروة الموسم). صدق: تقدير مرصود لا قياس موقعيّ — الحدود/ML تحتاج معايرة (تُعلَن).
    """
    fc = fractional_cover_from_ndvi(ndvi, ndvi_bare, ndvi_full)
    kd = density_coefficient_kd(fc, crop_height_m, ml)
    return kcb_full * kd, fc


# ─────────────────────────────────────────────────────────────────────
# عمق الجذور الديناميكيّ Zr ونطاق الماء المتاح TAW — FAO-56 §8 (نموّ الجذور)
# ─────────────────────────────────────────────────────────────────────
# عمق منطقة الجذور Zr ليس ثابتاً: ينمو من قيمة ابتدائيّة (Zr_min، عمق البذرة/
# الشتلة) إلى أقصى عمق فعّال (Zr_max) مع تطوّر المحصول. FAO-56 (الفصل ٨، حول
# Eq. 82–84) يَنمذِج هذا تقريبيّاً بنموّ **خطّيّ** بدلالة الأيّام بعد الزراعة (DAP)
# حتى بلوغ العمق الأقصى عند نهاية مرحلة التطوّر (development). عمق الجذور يحدّد
# سَعَة الخزّان: TAW = 1000·(θFC − θWP)·Zr (FAO-56 Eq. 82). جذور أعمق ⇒ خزّان
# أكبر ⇒ فترات ريّ أطول.
#
# الدوالّ هنا **نقيّة وإضافيّة**: لا تمسّ المسار المفرد (compute_irrigation) ولا
# المزدوج (compute_etc_dual). تُستخدَم لاحقاً في توأم/دفتر المياه عند الحاجة لـTAW
# ديناميكيّ بدل ثابت SoilZone.taw_mm_per_m.
#
# ⚠️ صدق صارم — تحتاج معايرة محلّيّة:
#   • Zr_min/Zr_max تقديريّة لكلّ محصول (FAO-56 Table 22 يعطي مدًى نوعيّاً،
#     والقيم الموقعيّة تتأثّر بالتربة/الصنف/طبقة صلبة محتملة). تُمرَّر صراحةً.
#   • θFC/θWP أدناه قيم نوعيّة حسب القوام (FAO-56 Table 19، عمود «Available
#     water» ووسطيّات شائعة) — تقديرات لا قياسات موقعيّة. القوام المجهول ⇒ "loam".


# θFC/θWP (محتوى الماء الحجميّ، m³/m³) حسب القوام — FAO-56 Table 19 (وسطيّات نوعيّة).
# θFC = السعة الحقليّة (Field Capacity)، θWP = نقطة الذبول (Wilting Point).
# الفرق (θFC − θWP) = الماء المتاح الكلّيّ لكلّ متر عمق. قيم تقديريّة تحتاج معايرة.
_THETA_FC_WP_BY_TEXTURE: dict[str, tuple[float, float]] = {
    # texture: (θFC, θWP)  m³/m³
    "sand": (0.10, 0.04),
    "sandy": (0.10, 0.04),
    "loamy sand": (0.12, 0.05),
    "sandy loam": (0.18, 0.07),
    "loam": (0.25, 0.10),
    "silt loam": (0.28, 0.11),
    "silt": (0.30, 0.12),
    "clay loam": (0.32, 0.16),
    "silty clay": (0.36, 0.21),
    "clay": (0.38, 0.24),
    "mixed": (0.25, 0.10),
}


def theta_fc_wp_for_texture(texture: str) -> tuple[float, float]:
    """يُرجِع (θFC, θWP) بـm³/m³ لقوام تربة، من جدول FAO-56 الافتراضيّ (Table 19).

    ⚠️ افتراض صريح: قيم نوعيّة وسطيّة حسب القوام — تقديرات لا قياسات موقعيّة،
    تحتاج معايرة محلّيّة (θFC/θWP الفعليّان يُقاسان مخبريّاً/حقليّاً). القوام
    المجهول ⇒ "loam".
    """
    return _THETA_FC_WP_BY_TEXTURE.get(texture.strip().lower(), _THETA_FC_WP_BY_TEXTURE["loam"])


def root_depth_m(
    days_after_planting: float,
    zr_min: float,
    zr_max: float,
    days_to_max: float,
) -> float:
    """عمق منطقة الجذور Zr (m) بنموّ خطّيّ بدلالة الأيّام بعد الزراعة — FAO-56 §8.

        Zr = Zr_min + (Zr_max − Zr_min)·min(1, DAP/days_to_max)

    مقصوص إلى ``[zr_min, zr_max]``. ``days_to_max`` = الأيّام حتى بلوغ العمق
    الأقصى (عادةً نهاية مرحلة التطوّر development — انظر ``root_depth_for_crop``).

    سلوك حدوديّ معرَّف:
      • DAP ≤ 0 ⇒ Zr = zr_min (لم تنمُ الجذور بعد).
      • DAP ≥ days_to_max ⇒ Zr = zr_max (بلغت العمق الأقصى).
      • الوسط ⇒ خطّيّ.
      • days_to_max ≤ 0 (غير صالح) ⇒ Zr = zr_max فوراً (نموّ لحظيّ — سلوك آمن).

    ⚠️ صدق: ``zr_min``/``zr_max`` تقديريّة لكلّ محصول (FAO-56 Table 22 مدًى نوعيّ)
    وتحتاج معايرة محلّيّة (تربة/صنف/طبقة صلبة).
    """
    if days_after_planting <= 0.0:
        return zr_min
    if days_to_max <= 0.0:
        return zr_max
    frac = min(1.0, days_after_planting / days_to_max)
    zr = zr_min + (zr_max - zr_min) * frac
    # قصّ دفاعيّ للنطاق (يحمي من zr_min > zr_max أو frac خارج [0,1]).
    lo, hi = (zr_min, zr_max) if zr_min <= zr_max else (zr_max, zr_min)
    return max(lo, min(hi, zr))


def root_depth_for_crop(
    profile: CropKcProfile,
    days_after_planting: float,
    zr_min: float,
    zr_max: float,
) -> float:
    """عمق الجذور Zr (m) لمحصول، مع اشتقاق ``days_to_max`` من ``profile.stage_days``.

    العمق الأقصى يُبلَغ عند نهاية مرحلة التطوّر (development) = ``stage_days[0] +
    stage_days[1]`` (نهاية initial + development) — اتّفاقاً مع منحنى Kc حيث تكتمل
    تغطية الأرض عند نهاية development. غلاف رفيق لـ``root_depth_m``.

    ⚠️ صدق: ``zr_min``/``zr_max`` تقديريّة لكلّ محصول، تحتاج معايرة محلّيّة.
    """
    s_ini, s_dev = profile.stage_days[0], profile.stage_days[1]
    days_to_max = float(s_ini + s_dev)
    return root_depth_m(days_after_planting, zr_min, zr_max, days_to_max)


def taw_from_root_depth(
    zr_m: float,
    texture: str = "loam",
    *,
    theta_fc: float | None = None,
    theta_wp: float | None = None,
) -> float:
    """الماء المتاح الكلّيّ TAW (mm) من عمق الجذور — FAO-56 Eq. 82.

        TAW = 1000·(θFC − θWP)·Zr

    ``θFC``/``θWP`` (m³/m³): إن غابا ⇒ من جدول القوام (``theta_fc_wp_for_texture``).
    ``Zr`` بالمتر. النتيجة (mm) ماء مُتاح بين السعة الحقليّة ونقطة الذبول في عمق
    الجذور. تزيد طرديّاً مع Zr (خزّان أعمق ⇒ ماء أكثر) ومع (θFC − θWP). مقصوصة ≥ 0.

    ⚠️ صدق: θFC/θWP الجدوليّة تقديريّة حسب القوام (FAO-56 Table 19) — تحتاج معايرة
    محلّيّة؛ Zr نفسه تقديريّ (انظر ``root_depth_m``).
    """
    if theta_fc is None or theta_wp is None:
        fc_def, wp_def = theta_fc_wp_for_texture(texture)
        theta_fc = fc_def if theta_fc is None else theta_fc
        theta_wp = wp_def if theta_wp is None else theta_wp
    return max(0.0, 1000.0 * (theta_fc - theta_wp) * max(0.0, zr_m))


@dataclass
class DualKcResult:
    """نتيجة الحساب المزدوج لمعامل المحصول (FAO-56 Ch.7)."""

    et0_mm: float
    kcb: float
    ks: float
    kc_max: float
    kr: float
    few: float
    ke: float
    kc_dual: float  # Kcb·Ks + Ke (المعامل الفعّال المركّب)
    etc_dual_mm: float  # (Kcb·Ks + Ke)·ET0
    etc_single_mm: float  # Kc·Ks·ET0 (للمقارنة الشفّافة)
    stage: str
    assumptions: list[str] = field(default_factory=list)


def compute_etc_dual(
    weather: WeatherDay,
    crop: CropKcProfile,
    days_after_planting: int,
    *,
    soil_ece: float | None = 0.0,
    de_mm: float = 0.0,
    tew_mm: float | None = None,
    rew_mm: float | None = None,
    texture: str = "loam",
    fc: float | None = None,
    fw: float = 1.0,
    rh_min_pct: float | None = None,
    crop_height_m: float = 0.5,
    kcb_offset: float = 0.05,
    ndvi: float | None = None,
    ndvi_bare: float = 0.15,
    ndvi_full: float = 0.85,
    et0_override: float | None = None,
) -> DualKcResult:
    """يحسب ETc بنهج المعامل المزدوج FAO-56 (Eq. 80) — إضافيّ واختياريّ.

        ETc = (Kcb · Ks + Ke) · ET0

    Ke يفصل التبخّر السطحيّ ويرفع ETc على التربة العارية/المبكّرة؛ Ks يُخفّض
    الأساس تحت الإجهاد الملحيّ/المائيّ. هذا المسار **لا يكسر** المسار المفرد
    (compute_irrigation) الذي يبقى الافتراضيّ.

    المُدخلات (مع افتراضات صريحة حين تغيب):
      de_mm     استنزاف الطبقة السطحيّة (mm). الافتراضيّ 0 = سطح مبلّل حديثاً
                (Ke أعلى ما يكون). مرّر De الفعليّ من موازنة الماء السطحيّ.
      tew/rew   إن غابا ⇒ من جدول FAO-56 حسب `texture` (tew_rew_for_texture).
      fc        كسر الغطاء النباتيّ. إن غاب ⇒ يُقدَّر من (Kcb−Kc_min)/(Kc_max−Kc_min)
                (FAO-56 Eq. 76 المبسّطة) — تقدير لا قياس.
      fw        كسر السطح المبلّل (1=رّيّ سطحيّ/مطر، ~0.3=تنقيط).
      rh_min    إن غاب ⇒ يُقرَّب من الرطوبة المتوسّطة في WeatherDay (افتراض).
      crop_height_m, kcb_offset  بارامترات FAO-56 افتراضيّة موثّقة.
      ndvi      إن مُرِّر (من raster-service) ⇒ يُشتقّ Kcb وfc **رصداً** منه (FAO-56 Eq. 76:
                fc(NDVI) → Kd → Kcb=Kcb_full·Kd) بدل اشتقاق Kcb من العمر — أصدق للحقل الفعليّ.
                ``ndvi_bare``/``ndvi_full`` حدود المعايرة (افتراضيّة، تحتاج ضبطاً محلّيّاً).
      soil_ece  ``None`` ⇒ الملوحة غير مطبّقة (Ks=1، off افتراضيّاً — قرار H5)؛ رقم ⇒ Ks من Maas-Hoffman.
      et0_override  إن مُرِّر ⇒ يُستعمَل بدل ET0 الداخليّ (penman) — لإبقاء ET0 مصدراً واحداً موحّداً (SSOT).

    ⚠️ القيود (صدق منهجيّ): Kcb مُشتقّ بإزاحة من Kc المدمج لا من بطاقة Kcb
    مُعايَرة؛ موازنة ماء الطبقة السطحيّة (De) تُمرَّر من الخارج ولا تُحتسب هنا
    تراكميّاً؛ TEW/REW افتراضيّة جدوليّة ما لم تُمرَّر صراحةً. النتيجة سليمة
    اتّجاهيّاً وكمّياً ضمن تساهُل FAO-56، لكنّها ليست قياساً موقعيّاً.
    """
    assumptions: list[str] = []

    # 1. ET0 — المتغيّر (طقس). et0_override يُمرَّر ET0 الكنسيّ الموحّد (H4/SSOT) فيستعمله
    # النهج المزدوج بدل إعادة حسابه داخليّاً — كي يبقى ET0 مصدراً واحداً متّسقاً مع الحالة.
    if et0_override is not None:
        et0 = float(et0_override)
        assumptions.append("ET0 من المصدر الكنسيّ الموحّد (et0_override) لا إعادة حساب داخليّ")
    else:
        et0 = penman_monteith_et0(weather)

    # 2. Kcb — الأساس (نتح). مرصود من NDVI (FAO-56 Eq. 76) إن توفّر، وإلّا من عمر المحصول.
    _, stage = kcb_for_age(crop, days_after_planting, kcb_offset=kcb_offset)
    ndvi_fc: float | None = None
    if ndvi is not None:
        # Kcb_full = Kcb عند الغطاء الكامل (ذروة الموسم kc_mid مطروحاً منها الإزاحة).
        kcb_full = max(0.15, crop.kc_mid - kcb_offset)
        kcb, ndvi_fc = kcb_from_ndvi(
            ndvi, kcb_full, crop_height_m, ndvi_bare=ndvi_bare, ndvi_full=ndvi_full
        )
        assumptions.append(
            f"Kcb مرصود من NDVI={ndvi:.2f} عبر Kd (FAO-56 Eq. 76؛ Kcb_full={kcb_full:.2f}، "
            f"NDVI_bare/full={ndvi_bare:.2f}/{ndvi_full:.2f}) — تقدير يحتاج معايرة محلّيّة"
        )
    else:
        kcb, _ = kcb_for_age(crop, days_after_planting, kcb_offset=kcb_offset)
        assumptions.append(f"Kcb مُشتقّ بإزاحة {kcb_offset:.2f} أسفل Kc المدمج (لا بطاقة Kcb مُعايَرة)")

    # 3. Ks — إجهاد ملحيّ (يُعاد استخدام منطق Maas-Hoffman القائم). soil_ece=None ⇒ الملوحة
    # **غير مطبّقة** (Ks=1.0) — قرار H5: off افتراضيّاً، لا تُدخَل ضمنيّاً في النهج المزدوج.
    if soil_ece is None:
        ks = 1.0
        assumptions.append("الملوحة غير مطبّقة (Ks=1، off افتراضيّاً — قرار H5)")
    else:
        ks = salinity_stress_ks(crop, soil_ece)

    # 4. TEW/REW — قياسيّة أو من الجدول حسب القوام
    if tew_mm is None or rew_mm is None:
        t_def, r_def = tew_rew_for_texture(texture)
        tew_mm = t_def if tew_mm is None else tew_mm
        rew_mm = r_def if rew_mm is None else rew_mm
        assumptions.append(
            f"TEW/REW من جدول FAO-56 للقوام «{texture}» (TEW={tew_mm:.0f}, REW={rew_mm:.0f} mm)"
        )

    # 5. RHmin — افتراض من الرطوبة المتوسّطة إن غاب
    if rh_min_pct is None:
        rh_min_pct = weather.humidity_pct
        assumptions.append("RHmin غير متوفّر ⇒ استُخدمت الرطوبة المتوسّطة (افتراض)")

    # 6. Kc_max — الحدّ الأعلى (Eq. 72)
    kcmax = kc_max(kcb, weather.wind_speed_m_s, rh_min_pct, crop_height_m)

    # 7. fc — كسر الغطاء: مرصود من NDVI إن توفّر، وإلّا مُقدَّر من Kcb (Eq. 76 المبسّطة)
    if fc is None and ndvi_fc is not None:
        fc = ndvi_fc
        assumptions.append(f"fc مرصود من NDVI={ndvi:.2f} (fc={fc:.2f}) — أصدق من تقدير Kcb")
    elif fc is None:
        kc_min = 0.15  # تربة عارية جافّة (FAO-56)
        denom = max(0.01, kcmax - kc_min)
        fc = max(0.0, min(0.99, (kcb - kc_min) / denom))
        assumptions.append("fc مُقدَّر من (Kcb−Kc_min)/(Kc_max−Kc_min) (Eq. 76) — تقدير")

    # 8. Kr و few و Ke
    kr = evaporation_reduction_kr(de_mm, tew_mm, rew_mm)
    few = few_exposed_wetted(fc, fw)
    # Eq. 71: Ke محدود بكلٍّ من الطاقة المتبقّية والكسر المبلّل المكشوف
    ke = min(kr * (kcmax - kcb), few * kcmax)
    ke = max(0.0, ke)

    # 9. ETc المزدوج (Eq. 80) + المفرد للمقارنة الشفّافة
    kc_dual = kcb * ks + ke
    etc_dual = kc_dual * et0
    kc_single, _ = kc_for_age(crop, days_after_planting)
    etc_single = kc_single * ks * et0

    return DualKcResult(
        et0_mm=round(et0, 2),
        kcb=round(kcb, 3),
        ks=round(ks, 3),
        kc_max=round(kcmax, 3),
        kr=round(kr, 3),
        few=round(few, 3),
        ke=round(ke, 3),
        kc_dual=round(kc_dual, 3),
        etc_dual_mm=round(etc_dual, 2),
        etc_single_mm=round(etc_single, 2),
        stage=stage.value,
        assumptions=assumptions,
    )


# ── Leaching requirement (FAO-56 Ch.8 Eq.82) ─────────────────────────
def leaching_requirement(water_ec: float, crop_threshold_ece: float) -> float:
    """Fraction of extra water needed to flush salts.
    LR = EC_w / (5 * EC_e - EC_w)   (FAO-56 Eq. 82)
    """
    denom = 5.0 * crop_threshold_ece - water_ec
    if denom <= 0:
        return 0.5  # cap — extreme salinity, capped leaching fraction
    return max(0.0, min(0.5, water_ec / denom))


# ── Soil zone (the SPATIAL constant — varies WITHIN a field) ─────────
@dataclass
class SoilZone:
    """A management zone. A field is NOT one soil — sandy/loam/mixed.
    Discussed: same weather, same Kc, but soil differs per zone.
    """

    zone_id: str
    texture: str  # sandy | loam | clay | mixed
    taw_mm_per_m: float  # total available water
    raw_fraction: float  # readily available fraction (p)
    ke_factor: float  # surface evaporation multiplier
    drainage: str  # fast | medium | slow
    area_ha: float
    source: str = "FAO-56 Table 19 (TAW by texture)"


# ── Main computation ─────────────────────────────────────────────────
@dataclass
class IrrigationResult:
    zone_id: str
    texture: str
    et0_mm: float
    kc: float
    stage: str
    etc_mm: float
    ks_salinity: float
    etc_adjusted_mm: float
    effective_rainfall_mm: float
    leaching_fraction: float
    net_irrigation_mm: float
    gross_irrigation_mm: float
    m3_per_ha: float
    total_m3_zone: float
    irrigation_interval_days: float
    night_irrigation_recommended: bool
    dtr_c: float
    salinity_applied: bool = False
    notes: list[str] = field(default_factory=list)


def compute_irrigation(
    weather: WeatherDay,
    crop: CropKcProfile,
    zone: SoilZone,
    days_after_planting: int,
    soil_ece: float,
    water_ec: float,
    effective_rainfall_mm: float = 0.0,
    irrigation_efficiency: float = 0.85,
    apply_salinity: bool = False,
) -> IrrigationResult:
    """Full FAO-56 chain for ONE zone on ONE day.

    Run this per-zone to produce a Variable-Rate Irrigation (VRA) map.

    قرار المستخدم (H5): الملوحة مفتاح صريح مُطفأ افتراضيّاً — «بلا ملوحة افتراضيّاً،
    قابلة للإدخال في أيّ مرحلة». لا يعتمد المفتاح على وجود ECe.
      - apply_salinity=False (افتراضيّ): Ks=1.0 وLR=0.0 ⇒ لا خفض ملوحة ولا غسيل.
      - apply_salinity=True: المسار القائم تماماً — salinity_stress_ks (Eq.81) +
        leaching_requirement (Eq.82). الصيغ الرياضيّة لم تتغيّر؛ صارت opt-in فقط.
    """
    notes: list[str] = []

    # 1. ET0 — the variable (weather)
    et0 = penman_monteith_et0(weather)

    # 2. Kc — the constant (crop + age)
    kc, stage = kc_for_age(crop, days_after_planting)

    # 3. ETc standard
    etc = et0 * kc

    # 4. soil-texture surface evap adjustment (sandy loses more)
    etc_zone = etc * zone.ke_factor

    # 5. salinity stress — opt-in (off by default per H5; Ks=1.0 when off)
    if apply_salinity:
        ks = salinity_stress_ks(crop, soil_ece)
    else:
        ks = 1.0
    etc_adj = etc_zone * ks
    if ks < 1.0:
        notes.append(
            f"إجهاد ملحي: EC={soil_ece} يتجاوز عتبة {crop.salt_tolerance_ece} (Ks={ks:.2f})"
        )

    # 6. net irrigation (minus effective rainfall)
    net = max(0.0, etc_adj - effective_rainfall_mm)

    # 7. leaching + efficiency -> gross — leaching only when salinity opt-in (else LR=0.0)
    if apply_salinity:
        lr = leaching_requirement(water_ec, crop.salt_tolerance_ece)
    else:
        lr = 0.0
    gross = (net * (1.0 + lr)) / irrigation_efficiency

    # irrigation interval from RAW (FAO-56 Ch.8)
    raw_mm = zone.taw_mm_per_m * zone.raw_fraction
    interval = raw_mm / etc_adj if etc_adj > 0 else 999.0

    # DTR + night irrigation (design decision: night irr saves 20-30% evap)
    dtr = weather.diurnal_range_c
    night = weather.temp_max_c >= 35.0  # hot day -> irrigate at night/dawn
    if night:
        notes.append("اسقِ فجراً أو ليلاً — تبخّر أقل في الجوّ البارد")
    if dtr > 15.0:
        notes.append(f"تباين حراري كبير (DTR={dtr:.0f}°م) — ميزة لجودة المحصول")

    m3_ha = gross * 10.0  # 1 mm = 10 m3/ha
    return IrrigationResult(
        zone_id=zone.zone_id,
        texture=zone.texture,
        et0_mm=round(et0, 2),
        kc=round(kc, 3),
        stage=stage.value,
        etc_mm=round(etc, 2),
        ks_salinity=round(ks, 3),
        etc_adjusted_mm=round(etc_adj, 2),
        effective_rainfall_mm=round(effective_rainfall_mm, 2),
        leaching_fraction=round(lr, 3),
        net_irrigation_mm=round(net, 2),
        gross_irrigation_mm=round(gross, 2),
        m3_per_ha=round(m3_ha, 1),
        total_m3_zone=round(m3_ha * zone.area_ha, 0),
        irrigation_interval_days=round(interval, 1),
        night_irrigation_recommended=night,
        dtr_c=round(dtr, 1),
        salinity_applied=apply_salinity,
        notes=notes,
    )


# ── مراجعة #3: GDD تراكمي من الطقس (ربط Open-Meteo) ──
def gdd_daily(tmax: float, tmin: float, tbase: float = 10.0) -> float:
    """درجات النمو اليومية (Growing Degree Days).
    tbase افتراضي 10°م (قمح/ذرة). يُجمع تراكمياً عبر الموسم."""
    tmean = (tmax + tmin) / 2.0
    return max(0.0, tmean - tbase)


def gdd_accumulate(weather_days: list[dict], tbase: float = 10.0) -> float:
    """يجمع GDD التراكمي من أيام طقس (كل يوم: {'tmax':.., 'tmin':..}).
    يربط مخرجات weather_openmeteo بحساب مرحلة النمو — بدل GDD اليدوي."""
    return round(sum(gdd_daily(d["tmax"], d["tmin"], tbase) for d in weather_days), 1)
