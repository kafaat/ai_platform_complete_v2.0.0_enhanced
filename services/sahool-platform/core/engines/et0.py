"""core/engines/et0.py — مصدر واحد لحساب ET0 (FAO-56).

يوحّد نواة **Hargreaves-Samani** والإشعاع خارج الغلاف **Ra** اللذين كانا مُكرَّرين
يدويّاً في ثلاث وحدات (`api/water_balance`, `api/weather_analytics`, `api/season_simulation`)
بقيم Ra متعارضة (محسوب / 14.0 / 15.0 ثابتة) — أعلى مخاطر «تكرار الصيغة» (انجراف صامت)
في تقرير الفجوات (H4). النواة **نقيّة** بلا تبعيّة على dataclasses الطقس (تأخذ قيماً
أوّليّة) ⇒ قابلة لإعادة الاستخدام من أيّ طبقة.

ملاحظة نطاق: Penman-Monteith ما يزال بنسختين (water_balance يأخذ WeatherInput، fao56
يأخذ WeatherDay) — توحيده يتطلّب التوفيق بين نوعَي الإدخال، فأُجِّل كمتابعة (لم يُلمَس هنا).
"""

from __future__ import annotations

import math

# Ra افتراضيّ (mm/يوم، مكافئ تبخّر) حين تغيب البيانات الجغرافيّة (خطّ عرض/يوم) — مسار
# fallback نادر فقط. اليمن ~12–18°N ومتوسّط Ra السنويّ مرتفع ⇒ 15.0. **توحيد**: كان
# season_simulation يستعمل 15.0 و weather_analytics 14.0 (للأشهر الغائبة من جدولها)؛
# وُحِّدا هنا على 15.0. القيمة الحقيقيّة تُحسب متى توفّر خطّ العرض عبر الدوالّ أدناه.
DEFAULT_RA_MM = 15.0

# تحويل Ra من MJ/m²/يوم إلى مكافئ تبخّر mm/يوم (FAO-56).
_MJ_TO_MM = 0.408


def extraterrestrial_radiation_mj(lat_deg: float, doy: int) -> float:
    """الإشعاع خارج الغلاف الجوّي Ra (MJ/m²/يوم) — FAO-56 eq. 21."""
    lat = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)  # المسافة الشمسيّة النسبيّة
    decl = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)  # الميل الشمسي
    ws = math.acos(max(-1, min(1, -math.tan(lat) * math.tan(decl))))  # زاوية الغروب
    gsc = 0.0820  # الثابت الشمسي MJ/m²/min
    return (
        (24 * 60 / math.pi)
        * gsc
        * dr
        * (ws * math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.sin(ws))
    )


def extraterrestrial_radiation_mm(lat_deg: float, doy: int) -> float:
    """Ra معبَّراً عنه بمكافئ التبخّر (mm/يوم) = Ra_MJ × 0.408."""
    return extraterrestrial_radiation_mj(lat_deg, doy) * _MJ_TO_MM


def hargreaves_et0(
    t_max_c: float,
    t_min_c: float,
    ra_mm: float,
    t_mean_c: float | None = None,
) -> float:
    """نواة Hargreaves-Samani — FAO-56 eq. 52. `ra_mm`: Ra بمكافئ التبخّر (mm/يوم).

    ET0 = 0.0023 × (Tmean+17.8) × √(Tmax−Tmin) × Ra_mm
    (Tmean الافتراضيّ = (Tmax+Tmin)/2 إن لم يُمرَّر صراحةً.)
    """
    tmean = t_mean_c if t_mean_c is not None else (t_max_c + t_min_c) / 2.0
    td = max(0.0, t_max_c - t_min_c)
    return max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(td) * ra_mm)


def hargreaves_et0_geo(
    t_max_c: float,
    t_min_c: float,
    lat_deg: float,
    doy: int,
    t_mean_c: float | None = None,
) -> float:
    """Hargreaves مع Ra محسوب من (خطّ العرض، اليوم) — الأدقّ حين تتوفّر الجغرافيا."""
    return hargreaves_et0(t_max_c, t_min_c, extraterrestrial_radiation_mm(lat_deg, doy), t_mean_c)


def penman_monteith_et0(
    t_max_c: float,
    t_min_c: float,
    t_mean_c: float,
    solar_rad_mj_m2: float,
    rh_mean_pct: float,
    wind_2m_ms: float,
    lat_deg: float,
    elevation_m: float,
    doy: int,
) -> float:
    """نواة FAO-56 Penman-Monteith (eq. 6) — قيم أوّليّة لا dataclass (H4).

    توحّد نسختين كانتا مكرّرتين حرفيّاً: `api/water_balance.et0_penman_monteith`
    (WeatherInput) و`core/engines/fao56.penman_monteith_et0` (WeatherDay). تأخذ
    `t_mean_c` صريحاً ليحفظ كلٌّ من الغلافين دلالته (water_balance قد يستعمل t_mean_c
    صريحاً؛ fao56 يستعمل (Tmax+Tmin)/2).

    الحالة الحدّيّة Rso≤0 (غير قابلة للوصول لخطوط عرض/ارتفاعات واقعيّة، Ra>0 دوماً)
    تستعمل الاحتياط 1.0 — يحفظ القيمة المرجعيّة المُثبتة في water_balance.
    """

    def _svp(t: float) -> float:  # ضغط البخار المشبع — eq. 11
        return 0.6108 * math.exp(17.27 * t / (t + 237.3))

    es = (_svp(t_max_c) + _svp(t_min_c)) / 2.0
    ea = es * rh_mean_pct / 100.0  # ضغط البخار الفعليّ
    delta = 4098.0 * _svp(t_mean_c) / (t_mean_c + 237.3) ** 2  # ميل المنحنى — eq. 13
    p = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26  # الضغط الجوّي — eq. 7
    gamma = 0.000665 * p  # الثابت السيكرومتري — eq. 8
    rns = (1.0 - 0.23) * solar_rad_mj_m2  # الموجة القصيرة (albedo 0.23)
    ra = extraterrestrial_radiation_mj(lat_deg, doy)
    rso = (0.75 + 2e-5 * elevation_m) * ra
    rs_rso = min(1.0, solar_rad_mj_m2 / rso) if rso > 0 else 1.0
    tmaxk = t_max_c + 273.16
    tmink = t_min_c + 273.16
    rnl = (  # صافي الموجة الطويلة — eq. 39
        4.903e-9
        * (tmaxk**4 + tmink**4)
        / 2.0
        * (0.34 - 0.14 * math.sqrt(ea))
        * (1.35 * rs_rso - 0.35)
    )
    rn = rns - rnl
    g = 0.0  # تدفّق حراريّ أرضيّ يوميّ ≈ 0
    num = 0.408 * delta * (rn - g) + gamma * 900.0 / (t_mean_c + 273.0) * wind_2m_ms * (es - ea)
    den = delta + gamma * (1.0 + 0.34 * wind_2m_ms)
    return max(0.0, num / den)
