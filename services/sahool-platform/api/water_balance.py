"""
api/water_balance.py — توصية ميزان الماء (ET0 + المطر)

خارطة الطريق: المرحلة ٢، البند ١٢. الأعلى صلة بأزمة المياه اليمنيّة
(الزراعة تستهلك ٩٠٪ من سحب المياه؛ القات ٣٠٪).

يحسب الاحتياج المائي:
  ET0 (التبخّر-نتح المرجعي) → ETc = ET0 × Kc (معامل المحصول حسب المرحلة)
  → الاحتياج الصافي = ETc − المطر الفعّال → عمق/فترة الريّ الموصى بها.

طريقتان:
  • FAO-56 Penman-Monteith (الأدقّ) — يحتاج إشعاع/رطوبة/رياح
  • Hargreaves-Samani (احتياطي) — حرارة فقط (مهمّ: المحطّات اليمنيّة قليلة)

المبدأ: "human-in-the-loop" — توصية لا ريّ آلي مغلق (رفضناه سابقاً).

⚠ معاملات Kc تقديريّة من FAO-56 (مرجع علمي)، لكن يجب معايرتها محلّيّاً.
موسومة بمصدرها. الحساب الفيزيائي (Penman-Monteith) معادلة معياريّة لا ثابت مُختلق.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# مصدر ET0 الموحّد (H4): نواة Hargreaves + Ra. لا نُعيد كتابة الصيغة هنا.
from core.engines.et0 import (
    extraterrestrial_radiation_mj,
    hargreaves_et0_geo,
)
from core.engines.et0 import (
    penman_monteith_et0 as et0_penman_monteith_core,
)

# مصدر الحقيقة الوحيد لصيغ الملوحة (H5): Ks (Eq.81) + احتياج الغسيل (Eq.82).
# لا نُعيد كتابة الصيغة هنا — نفوّض إلى المحرّك مباشرةً (لا تكرار).
from core.engines.fao56 import (
    leaching_requirement as _fao56_leaching_requirement,
)
from core.engines.fao56 import (
    salinity_stress_ks as _fao56_salinity_stress_ks,
)
from core.season_phenology import crop_kc_profile, resolve_crop_id


class ET0Method(StrEnum):
    PENMAN_MONTEITH = "penman_monteith"
    HARGREAVES = "hargreaves_samani"


# معاملات Kc حسب مرحلة النموّ (FAO-56 Irrigation & Drainage Paper 56)
# ⚠ FAO reference values — تحتاج معايرة محلّيّة يمنيّة
# المراحل: initial / development / mid-season / late-season
KC_BY_CROP_STAGE: dict[str, dict[str, float]] = {
    "wheat": {"initial": 0.40, "development": 0.75, "mid": 1.15, "late": 0.40},
    "barley": {"initial": 0.40, "development": 0.75, "mid": 1.15, "late": 0.40},
    "sorghum": {"initial": 0.40, "development": 0.75, "mid": 1.10, "late": 0.55},
    "maize": {"initial": 0.40, "development": 0.80, "mid": 1.20, "late": 0.60},
    "millet": {"initial": 0.35, "development": 0.70, "mid": 1.00, "late": 0.35},
    "tomato": {"initial": 0.60, "development": 0.85, "mid": 1.15, "late": 0.80},
    "potato": {"initial": 0.50, "development": 0.85, "mid": 1.15, "late": 0.75},
    "onion": {"initial": 0.70, "development": 0.85, "mid": 1.05, "late": 0.75},
    "alfalfa": {"initial": 0.40, "development": 0.80, "mid": 1.20, "late": 1.15},
    "citrus": {"initial": 0.70, "development": 0.65, "mid": 0.70, "late": 0.70},
    "dates": {"initial": 0.90, "development": 0.95, "mid": 0.95, "late": 0.95},
}


@dataclass
class WeatherInput:
    """مدخلات الطقس اليوميّة."""

    t_min_c: float
    t_max_c: float
    t_mean_c: float | None = None
    # لـPenman-Monteith الكامل (اختياريّة — لو غابت نستخدم Hargreaves)
    solar_rad_mj_m2: float | None = None  # الإشعاع الشمسي MJ/m²/يوم
    rh_mean_pct: float | None = None  # الرطوبة النسبيّة %
    wind_2m_ms: float | None = None  # سرعة الرياح عند 2م m/s
    # سياق جغرافي (لـPenman-Monteith و Hargreaves)
    latitude_deg: float = 15.5  # اليمن ~15°N
    elevation_m: float = 2000.0  # الهضبة اليمنيّة
    day_of_year: int = 100

    @property
    def t_mean(self) -> float:
        return self.t_mean_c if self.t_mean_c is not None else (self.t_min_c + self.t_max_c) / 2


@dataclass
class WaterBalanceResult:
    et0_mm: float
    method: ET0Method
    kc: float
    etc_mm: float  # الاحتياج الكلّي
    effective_rain_mm: float
    net_irrigation_mm: float  # الاحتياج الصافي بعد المطر
    advice_ar: str
    kc_source_ar: str = "محصول مُعرّف"  # هل Kc خاصّ بالمحصول أم عامّ؟
    salinity_applied: bool = False  # هل طُبّق خطّاف الملوحة (Ks/غسيل)؟ افتراضيّاً off

    def to_dict(self) -> dict:
        d = {
            "et0_mm": round(self.et0_mm, 2),
            "method": self.method.value,
            "kc": self.kc,
            "kc_source_ar": self.kc_source_ar,
            "etc_mm": round(self.etc_mm, 2),
            "effective_rain_mm": round(self.effective_rain_mm, 2),
            "net_irrigation_mm": round(self.net_irrigation_mm, 2),
            "advice_ar": self.advice_ar,
        }
        # H5: الحقل يظهر فقط حين تُطبَّق الملوحة — off (الافتراضيّ) يحفظ شكل القاموس
        # القائم تماماً (لا انحدار على المستهلكين/الاختبارات). on ⇒ شفّافيّة opt-in.
        if self.salinity_applied:
            d["salinity_applied"] = self.salinity_applied
        return d


def _extraterrestrial_radiation(lat_deg: float, doy: int) -> float:
    """الإشعاع خارج الغلاف الجوّي Ra (MJ/m²/يوم) — FAO-56 eq. 21.

    يفوّض للمصدر الموحّد (core.engines.et0). يبقى الاسم لاستعمال Penman-Monteith أدناه.
    """
    return extraterrestrial_radiation_mj(lat_deg, doy)


def et0_hargreaves(w: WeatherInput) -> float:
    """Hargreaves-Samani ET0 (حرارة فقط) — FAO-56 eq. 52، عبر المصدر الموحّد.

    Ra محسوب من (خطّ العرض، اليوم). سلوك محفوظ تماماً (نفس الصيغة والثوابت).
    """
    return hargreaves_et0_geo(w.t_max_c, w.t_min_c, w.latitude_deg, w.day_of_year, w.t_mean)


def et0_penman_monteith(w: WeatherInput) -> float:
    """FAO-56 Penman-Monteith ET0 (mm/يوم) — eq. 6.

    يحتاج الإشعاع + الرطوبة + الرياح. لو غابت → استخدم Hargreaves.
    """
    if w.solar_rad_mj_m2 is None or w.rh_mean_pct is None or w.wind_2m_ms is None:
        raise ValueError("Penman-Monteith يحتاج solar_rad + rh + wind")

    # المصدر الموحّد (H4): نواة PM واحدة. نمرّر w.t_mean (يحترم t_mean_c الصريح).
    return et0_penman_monteith_core(
        w.t_max_c,
        w.t_min_c,
        w.t_mean,
        w.solar_rad_mj_m2,
        w.rh_mean_pct,
        w.wind_2m_ms,
        w.latitude_deg,
        w.elevation_m,
        w.day_of_year,
    )


def compute_et0(w: WeatherInput) -> tuple:
    """يحسب ET0 بأفضل طريقة متاحة. يعيد (et0, method)."""
    try:
        return et0_penman_monteith(w), ET0Method.PENMAN_MONTEITH
    except ValueError:
        return et0_hargreaves(w), ET0Method.HARGREAVES


def _effective_rain(rain_mm: float) -> float:
    """المطر الفعّال (USDA-SCS مبسّط): جزء من المطر يصل الجذور."""
    if rain_mm <= 0:
        return 0.0
    if rain_mm < 75:
        return rain_mm * (125 - 0.2 * rain_mm) / 125
    return 0.1 * rain_mm + 92.5


# حدود قصّ Kc الديناميكيّ — ⚠ UNVALIDATED: تحتاج معايرة يمنيّة (القات/البنّ/الذرة الرفيعة).
KC_DYN_MIN = 0.15
KC_DYN_MAX = 1.35


def kc_from_ndvi(ndvi: float | None, kc_map: dict, stage: str) -> tuple[float, float | None]:
    """Kc ديناميكيّ مُعكَس من NDVI عبر الغطاء النباتيّ (fAPAR) — دالّة نقيّة.

    محفوظة السلوك: NDVI غائب ⇒ تُرجِع Kc الثابت بالمرحلة تماماً (FAO-56). متاح ⇒
    تطعّم Kc خطّيّاً بين Kc الابتدائيّ (غطاء ضئيل) وKc الذرويّ (غطاء كامل) حسب fAPAR.
    تُرجِع (kc, fAPAR أو None). fAPAR = 1.24·NDVI−0.168 (Myneni & Williams 1994 —
    نفس صيغة season_simulation.fapar_from_ndvi و raster-service).
    """
    static_kc = kc_map.get(stage, 1.0)
    if ndvi is None:
        return static_kc, None
    fapar = min(1.0, max(0.0, 1.24 * ndvi - 0.168))
    kc_min = kc_map.get("initial", 0.4)
    kc_max = kc_map.get("mid", 1.1)
    kc = kc_min + (kc_max - kc_min) * fapar
    return min(KC_DYN_MAX, max(KC_DYN_MIN, kc)), fapar


# عتبة تأجيل الريّ التنبّؤيّ — ⚠ قرار منتَج قابل للمعايرة: المطر المتوقّع الفعّال ≥ هذه
# النسبة من الاحتياج الصافي ⇒ أجّل. المطر المتوقّع يضبط **التوقيت لا الكمّيّة** (صدق:
# لا نخصم مطراً قد لا يهطل من العمق الموصى به).
FORECAST_DEFER_FRACTION = 1.0
# ترشّح المطر الافتراضيّ (جزء من المطر المتوقّع يصل منطقة الجذور) — ⚠ قابل للمعايرة
# حسب التربة/الشدّة. المطر المتوقّع الفعّال = المتوقّع × ثقة التنبّؤ × الترشّح.
FORECAST_INFILTRATION_DEFAULT = 0.7


def _forecast_defer(
    net_mm: float,
    forecast_rain_mm: float | None,
    window_days: int,
    confidence: float = 1.0,
    infiltration: float = FORECAST_INFILTRATION_DEFAULT,
) -> str:
    """ملاحظة تأجيل عربيّة إن غطّى المطر المتوقّع **الفعّال** الاحتياج، وإلّا "" — نقيّة.

    المطر الفعّال = المتوقّع × ثقة التنبّؤ × عامل الترشّح (أدقّ من عتبة خام — صدق:
    مطر منخفض الاحتماليّة/ضعيف الترشّح لا يُؤجِّل). محفوظة السلوك: forecast_rain_mm
    غائب/≤0 أو لا احتياج (net≤0) ⇒ "" (لا تغيير).
    """
    if not forecast_rain_mm or forecast_rain_mm <= 0 or net_mm <= 0:
        return ""
    eff_fc = forecast_rain_mm * max(0.0, min(1.0, confidence)) * max(0.0, min(1.0, infiltration))
    if eff_fc >= net_mm * FORECAST_DEFER_FRACTION:
        return (
            f"⏸ أجّل الريّ — مطر متوقّع {forecast_rain_mm:.0f} مم (ثقة "
            f"{confidence * 100:.0f}% × ترشّح {infiltration:.1f} = {eff_fc:.1f} فعّال) "
            f"خلال {window_days} يوم يغطّي الاحتياج."
        )
    return ""


def _salinity_hook(
    crop: str,
    etc: float,
    net: float,
    soil_ece: float | None,
    water_ec: float | None,
) -> tuple[float, float, bool, str]:
    """خطّاف ملوحة اختياريّ (H5) — يفوّض لصيغ المحرّك (لا تكرار).

    يُستدعى فقط عند ``apply_salinity=True``. يبني :class:`CropKcProfile` للمحصول
    لقراءة عتبة تحمّل الملوحة، ثمّ:
      • يطبّق ``Ks = fao56.salinity_stress_ks(profile, soil_ece)`` على ETc (Eq.81).
      • (اختياريّاً) يضيف احتياج الغسيل ``LR = fao56.leaching_requirement(water_ec,
        threshold)`` فوق الاحتياج الصافي (Eq.82) حين توفّر ``water_ec``.

    صدق: تعذّر بناء البروفايل (بطاقة مفقودة/بلا kc) ⇒ off بصدق (لا ملوحة، لا غسيل،
    لا انحدار). يُرجِع ``(etc_adj, net_adj, applied, note_ar)``.
    """
    profile = crop_kc_profile(resolve_crop_id(crop))
    if profile is None:
        return etc, net, False, ""

    note_parts: list[str] = []
    etc_adj = etc
    if soil_ece is not None:
        ks = _fao56_salinity_stress_ks(profile, soil_ece)
        etc_adj = etc * ks
        if ks < 1.0:
            note_parts.append(
                f"إجهاد ملحيّ: ECe={soil_ece} يتجاوز العتبة "
                f"{profile.salt_tolerance_ece} (Ks={ks:.2f})."
            )
    # إعادة حساب الصافي على ETc المُعدَّل (المطر الفعّال يُخصَم من ETc المُجهَد).
    net_adj = max(0.0, etc_adj - (etc - net))
    if water_ec is not None:
        lr = _fao56_leaching_requirement(water_ec, profile.salt_tolerance_ece)
        if lr > 0.0 and net_adj > 0.0:
            net_adj = net_adj * (1.0 + lr)
            note_parts.append(f"غسيل الأملاح: +{lr * 100:.0f}% فوق الصافي (ECw={water_ec}).")
    return etc_adj, net_adj, True, " ".join(note_parts)


def water_balance(
    w: WeatherInput,
    crop: str,
    stage: str,
    rain_mm: float = 0.0,
    ndvi: float | None = None,
    forecast_rain_mm: float | None = None,
    forecast_window_days: int = 3,
    forecast_confidence: float = 1.0,
    forecast_infiltration: float = FORECAST_INFILTRATION_DEFAULT,
    soil_ece: float | None = None,
    water_ec: float | None = None,
    apply_salinity: bool = False,
) -> WaterBalanceResult:
    """يحسب توصية الريّ ليوم/فترة.

    Args:
        w: الطقس. crop: المحصول. stage: initial|development|mid|late.
        rain_mm: المطر في الفترة. ndvi: إن توفّر ⇒ Kc ديناميكيّ (وإلّا ثابت بالمرحلة).
        soil_ece: ملوحة التربة ECe (dS/m) — تُستخدم فقط مع ``apply_salinity=True``.
        water_ec: ملوحة ماء الريّ ECw (dS/m) — تُفعّل احتياج الغسيل مع الملوحة.
        apply_salinity: خطّاف الملوحة (H5). **افتراضيّاً off**: السلوك القائم تماماً
            (net = ETc − مطر فعّال، بلا Ks ولا غسيل). on ⇒ يطبّق Ks على ETc و(اختياريّاً)
            غسيلاً، بنفس صيغ المحرّك (``fao56``). الملوحة opt-in بقرار المستخدم.
    """
    et0, method = compute_et0(w)
    crop_known = crop in KC_BY_CROP_STAGE
    kc_map = KC_BY_CROP_STAGE.get(
        crop, {"initial": 0.4, "development": 0.8, "mid": 1.1, "late": 0.6}
    )
    kc_source = (
        f"محصول مُعرّف ({crop})"
        if crop_known
        else f"عامّ — '{crop}' غير مُعرّف، استُخدم منحنى Kc افتراضي (تقدير، عايِر ميدانيّاً)"
    )
    kc, kc_fapar = kc_from_ndvi(ndvi, kc_map, stage)
    if kc_fapar is not None:
        kc_source = f"Kc ديناميكيّ من NDVI={ndvi:.2f} (fAPAR={kc_fapar:.2f}) — عايِر يمنيّاً"
    etc = et0 * kc
    eff_rain = _effective_rain(rain_mm)
    net = max(0.0, etc - eff_rain)

    # خطّاف الملوحة (H5) — مُطفأ افتراضيّاً. off ⇒ السلوك أعلاه بلا أيّ تغيير (لا انحدار).
    salinity_note = ""
    salinity_applied = False
    if apply_salinity:
        etc, net, salinity_applied, salinity_note = _salinity_hook(
            crop, etc, net, soil_ece, water_ec
        )

    if net <= 0:
        advice = f"لا حاجة للريّ — المطر ({eff_rain:.1f} مم فعّال) يغطّي الاحتياج ({etc:.1f} مم)."
    elif net < 5:
        advice = f"احتياج منخفض: {net:.1f} مم. يُمكن تأجيل الريّ قليلاً."
    else:
        advice = (
            f"الاحتياج الصافي {net:.1f} مم (ETc {etc:.1f} − مطر فعّال {eff_rain:.1f}). "
            f"رُيّ بهذا العمق. الطريقة: {method.value}."
        )

    # ريّ تنبّؤيّ: المطر المتوقّع يُقدَّم كتأجيل (لا يُخصَم من net) — التوقيت لا الكمّيّة.
    defer_note = _forecast_defer(
        net, forecast_rain_mm, forecast_window_days, forecast_confidence, forecast_infiltration
    )
    if defer_note:
        advice = f"{defer_note} {advice}"

    # ملاحظة الملوحة (إن طُبّقت وكان لها أثر) تُلحَق بالتوصية — شفّافيّة المصدر.
    if salinity_note:
        advice = f"{advice} {salinity_note}"

    return WaterBalanceResult(
        et0_mm=et0,
        method=method,
        kc=kc,
        etc_mm=etc,
        effective_rain_mm=eff_rain,
        net_irrigation_mm=net,
        advice_ar=advice,
        kc_source_ar=kc_source,
        salinity_applied=salinity_applied,
    )
