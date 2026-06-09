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

import math
from dataclasses import dataclass
from enum import StrEnum


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

    def to_dict(self) -> dict:
        return {
            "et0_mm": round(self.et0_mm, 2),
            "method": self.method.value,
            "kc": self.kc,
            "kc_source_ar": self.kc_source_ar,
            "etc_mm": round(self.etc_mm, 2),
            "effective_rain_mm": round(self.effective_rain_mm, 2),
            "net_irrigation_mm": round(self.net_irrigation_mm, 2),
            "advice_ar": self.advice_ar,
        }


def _extraterrestrial_radiation(lat_deg: float, doy: int) -> float:
    """الإشعاع خارج الغلاف الجوّي Ra (MJ/m²/يوم) — FAO-56 eq. 21."""
    lat = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)  # المسافة الشمسيّة
    decl = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)  # الميل الشمسي
    ws = math.acos(max(-1, min(1, -math.tan(lat) * math.tan(decl))))  # زاوية الغروب
    gsc = 0.0820  # الثابت الشمسي MJ/m²/min
    ra = (
        (24 * 60 / math.pi)
        * gsc
        * dr
        * (ws * math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.sin(ws))
    )
    return ra


def et0_hargreaves(w: WeatherInput) -> float:
    """Hargreaves-Samani ET0 (حرارة فقط) — FAO-56 eq. 52.

    ET0 = 0.0023 × (Tmean+17.8) × √(Tmax−Tmin) × Ra×0.408
    (0.408 يحوّل Ra من MJ/m² إلى mm equivalent)
    """
    ra = _extraterrestrial_radiation(w.latitude_deg, w.day_of_year)
    td = max(0.0, w.t_max_c - w.t_min_c)
    return 0.0023 * (w.t_mean + 17.8) * math.sqrt(td) * ra * 0.408


def et0_penman_monteith(w: WeatherInput) -> float:
    """FAO-56 Penman-Monteith ET0 (mm/يوم) — eq. 6.

    يحتاج الإشعاع + الرطوبة + الرياح. لو غابت → استخدم Hargreaves.
    """
    if w.solar_rad_mj_m2 is None or w.rh_mean_pct is None or w.wind_2m_ms is None:
        raise ValueError("Penman-Monteith يحتاج solar_rad + rh + wind")

    t = w.t_mean

    # ضغط البخار المشبع es و الفعلي ea
    def svp(temp):  # FAO-56 eq. 11
        return 0.6108 * math.exp(17.27 * temp / (temp + 237.3))

    es = (svp(w.t_max_c) + svp(w.t_min_c)) / 2
    ea = es * w.rh_mean_pct / 100
    # ميل منحنى ضغط البخار Δ (eq. 13)
    delta = 4098 * svp(t) / (t + 237.3) ** 2
    # الثابت السيكرومتري γ (eq. 8) — يعتمد على الارتفاع
    p = 101.3 * ((293 - 0.0065 * w.elevation_m) / 293) ** 5.26
    gamma = 0.000665 * p
    # صافي الإشعاع Rn (تقدير مبسّط من الإشعاع الشمسي)
    rns = (1 - 0.23) * w.solar_rad_mj_m2  # الموجة القصيرة (albedo 0.23)
    ra = _extraterrestrial_radiation(w.latitude_deg, w.day_of_year)
    rso = (0.75 + 2e-5 * w.elevation_m) * ra
    tmaxk = w.t_max_c + 273.16
    tmink = w.t_min_c + 273.16
    rnl = (
        4.903e-9
        * (tmaxk**4 + tmink**4)
        / 2
        * (0.34 - 0.14 * math.sqrt(ea))
        * (1.35 * min(1.0, w.solar_rad_mj_m2 / rso if rso > 0 else 1) - 0.35)
    )
    rn = rns - rnl
    g = 0  # تدفّق حراري أرضي يومي ≈ 0
    u2 = w.wind_2m_ms
    # FAO-56 eq. 6
    num = 0.408 * delta * (rn - g) + gamma * 900 / (t + 273) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    return max(0.0, num / den)


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


def water_balance(
    w: WeatherInput,
    crop: str,
    stage: str,
    rain_mm: float = 0.0,
) -> WaterBalanceResult:
    """يحسب توصية الريّ ليوم/فترة.

    Args:
        w: الطقس. crop: المحصول. stage: initial|development|mid|late.
        rain_mm: المطر في الفترة.
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
    kc = kc_map.get(stage, 1.0)
    etc = et0 * kc
    eff_rain = _effective_rain(rain_mm)
    net = max(0.0, etc - eff_rain)

    if net <= 0:
        advice = f"لا حاجة للريّ — المطر ({eff_rain:.1f} مم فعّال) يغطّي الاحتياج ({etc:.1f} مم)."
    elif net < 5:
        advice = f"احتياج منخفض: {net:.1f} مم. يُمكن تأجيل الريّ قليلاً."
    else:
        advice = (
            f"الاحتياج الصافي {net:.1f} مم (ETc {etc:.1f} − مطر فعّال {eff_rain:.1f}). "
            f"رُيّ بهذا العمق. الطريقة: {method.value}."
        )

    return WaterBalanceResult(
        et0_mm=et0,
        method=method,
        kc=kc,
        etc_mm=etc,
        effective_rain_mm=eff_rain,
        net_irrigation_mm=net,
        advice_ar=advice,
        kc_source_ar=kc_source,
    )
