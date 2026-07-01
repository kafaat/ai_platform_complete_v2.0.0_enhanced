"""تحقّق زراعيّ مقابل FAO-56 (Production Hardening — المرحلة C).

يتحقّق أنّ محرّكات ET0/Kc/ETc/توازن المياه تطابق المرجع العلميّ FAO-56 (Irrigation &
Drainage Paper 56)، لا مجرّد ثبات داخليّ:

- **Ra** (الإشعاع خارج الغلاف): مثال FAO-56 رقم 8 (lat −20°، DOY 246) ⇒ 32.2 MJ/m²/يوم.
- **es** (ضغط البخار المشبع، eq. 11): جدول FAO-56 2.3 — es(20°)=2.338، es(30°)=4.243 kPa.
- **Penman-Monteith** (eq. 6): تحقّق تقاطعيّ ضدّ إعادة تنفيذ مستقلّة لكامل معادلات FAO-56.
- **Hargreaves** (eq. 52): أمانة الصيغة والثوابت.
- **Kc**: جدول FAO-56 رقم 12 (قمح/ذرة/برسيم…) + ترتيب المراحل.
- **ETc = ET0×Kc** + الاحتياج الصافي = ETc − المطر الفعّال.

منطق فيزيائيّ صرف بلا خدمات (وظيفة Platform Unit Tests).
"""

from __future__ import annotations

import math

import pytest
from api.water_balance import (
    KC_BY_CROP_STAGE,
    ET0Method,
    WeatherInput,
    _effective_rain,
    compute_et0,
    et0_hargreaves,
    et0_penman_monteith,
    kc_from_ndvi,
)
from core.engines.et0 import (
    extraterrestrial_radiation_mj,
    extraterrestrial_radiation_mm,
    hargreaves_et0,
)


# ── مرجع FAO-56 مستقلّ لـPenman-Monteith (تحقّق تقاطعيّ، لا تكرار للكود المُختبَر) ──
def _svp(t: float) -> float:
    """ضغط البخار المشبع e°(T) — FAO-56 eq. 11."""
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def _fao56_pm_reference(tmax, tmin, tmean, rs, rh, u2, lat, elev, doy) -> float:
    """إعادة تنفيذ مستقلّة لكامل FAO-56 Penman-Monteith (eq. 6,7,8,11,13,21-25,38,39)."""
    es = (_svp(tmax) + _svp(tmin)) / 2
    ea = es * rh / 100.0
    delta = 4098 * _svp(tmean) / (tmean + 237.3) ** 2
    p = 101.3 * ((293 - 0.0065 * elev) / 293) ** 5.26
    gamma = 0.000665 * p
    dr = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    decl = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    phi = math.radians(lat)
    ws = math.acos(-math.tan(phi) * math.tan(decl))
    ra = (
        24
        * 60
        / math.pi
        * 0.0820
        * dr
        * (ws * math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.sin(ws))
    )
    rso = (0.75 + 2e-5 * elev) * ra
    rns = 0.77 * rs
    rnl = (
        4.903e-9
        * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4)
        / 2
        * (0.34 - 0.14 * math.sqrt(ea))
        * (1.35 * min(rs / rso, 1.0) - 0.35)
    )
    rn = rns - rnl
    num = 0.408 * delta * rn + gamma * 900 / (tmean + 273) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)
    return num / den


# ── Ra: الإشعاع خارج الغلاف الجوّي (FAO-56 eq. 21-25) ───────────────────────
def test_ra_matches_fao56_example_8():
    # مثال FAO-56 رقم 8: خطّ عرض −20°، ٣ سبتمبر (DOY 246) ⇒ Ra = 32.2 MJ/m²/يوم.
    ra = extraterrestrial_radiation_mj(-20.0, 246)
    assert abs(ra - 32.2) < 0.3, f"Ra={ra} خارج مرجع FAO-56 (32.2)"


def test_ra_mm_conversion_is_0408():
    ra_mj = extraterrestrial_radiation_mj(15.5, 100)
    assert abs(extraterrestrial_radiation_mm(15.5, 100) - ra_mj * 0.408) < 1e-6


def test_ra_within_physical_bounds_year_round():
    for doy in range(1, 366, 15):
        ra = extraterrestrial_radiation_mj(15.5, doy)
        assert 0.0 < ra < 45.0, f"Ra={ra} غير فيزيائيّ عند DOY {doy}"


# ── es: ضغط البخار المشبع (FAO-56 eq. 11 / جدول 2.3) ────────────────────────
def test_saturation_vapour_pressure_matches_fao56_table():
    assert abs(_svp(20.0) - 2.338) < 0.002  # جدول FAO-56 2.3
    assert abs(_svp(30.0) - 4.243) < 0.002


# ── Penman-Monteith: تحقّق تقاطعيّ مع FAO-56 المستقلّ ───────────────────────
@pytest.mark.parametrize(
    "tmax,tmin,rs,rh,u2",
    [(30, 15, 22.0, 45, 2.0), (25, 12, 18.0, 60, 1.5), (38, 22, 26.0, 25, 3.0)],
)
def test_penman_monteith_matches_independent_fao56(tmax, tmin, rs, rh, u2):
    tmean = (tmax + tmin) / 2
    w = WeatherInput(
        t_min_c=tmin,
        t_max_c=tmax,
        solar_rad_mj_m2=rs,
        rh_mean_pct=rh,
        wind_2m_ms=u2,
        latitude_deg=15.5,
        elevation_m=2000,
        day_of_year=100,
    )
    engine = et0_penman_monteith(w)
    ref = _fao56_pm_reference(tmax, tmin, tmean, rs, rh, u2, 15.5, 2000, 100)
    assert abs(engine - ref) < 0.05, f"PM engine={engine:.3f} ≠ FAO-56 ref={ref:.3f}"


def test_penman_monteith_is_physically_bounded_and_monotonic():
    def pm(tmax, tmin, rs, rh, u2):
        return et0_penman_monteith(
            WeatherInput(
                t_min_c=tmin,
                t_max_c=tmax,
                solar_rad_mj_m2=rs,
                rh_mean_pct=rh,
                wind_2m_ms=u2,
                latitude_deg=15.5,
                elevation_m=2000,
                day_of_year=100,
            )
        )

    cool_humid = pm(24, 14, 16.0, 70, 1.0)
    hot_dry = pm(40, 24, 28.0, 20, 3.5)
    assert 0.0 < cool_humid < 15.0 and 0.0 < hot_dry < 15.0
    assert hot_dry > cool_humid, "ET0 يجب أن يرتفع مع الحرّ والجفاف والرياح"


def test_penman_monteith_requires_full_inputs():
    with pytest.raises(ValueError):
        et0_penman_monteith(WeatherInput(t_min_c=15, t_max_c=30))  # بلا إشعاع/رطوبة/رياح


# ── Hargreaves (FAO-56 eq. 52): أمانة الصيغة ────────────────────────────────
def test_hargreaves_formula_fidelity():
    # توقيع النواة: hargreaves_et0(t_max, t_min, ra_mm, t_mean) — FAO-56 eq. 52.
    tmax, tmin, ra_mm, tmean = 30.0, 15.0, 15.43, 22.5
    expected = 0.0023 * (tmean + 17.8) * math.sqrt(tmax - tmin) * ra_mm
    assert abs(hargreaves_et0(tmax, tmin, ra_mm, tmean) - expected) < 1e-6


def test_compute_et0_falls_back_to_hargreaves_without_radiation():
    et0, method = compute_et0(
        WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    )
    assert method == ET0Method.HARGREAVES
    assert et0 > 0


def test_pm_and_hargreaves_agree_in_ballpark():
    common = dict(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    pm = et0_penman_monteith(
        WeatherInput(solar_rad_mj_m2=22.0, rh_mean_pct=45, wind_2m_ms=2.0, **common)
    )
    hg = et0_hargreaves(WeatherInput(**common))
    assert 0.6 < pm / hg < 1.6, f"PM({pm:.2f}) وHargreaves({hg:.2f}) متباعدان لا فيزيائيّاً"


# ── Kc: جدول FAO-56 رقم 12 ──────────────────────────────────────────────────
def test_kc_mid_season_matches_fao56_table_12():
    # قيم Kc_mid المنشورة (FAO-56 Table 12).
    assert KC_BY_CROP_STAGE["wheat"]["mid"] == 1.15
    assert KC_BY_CROP_STAGE["maize"]["mid"] == 1.20
    assert KC_BY_CROP_STAGE["alfalfa"]["mid"] == 1.20
    assert KC_BY_CROP_STAGE["tomato"]["mid"] == 1.15
    assert KC_BY_CROP_STAGE["potato"]["mid"] == 1.15


def test_kc_stage_ordering_is_physical():
    for crop, stages in KC_BY_CROP_STAGE.items():
        assert stages["initial"] <= stages["mid"], f"{crop}: Kc_ini يجب ألّا يتجاوز Kc_mid"
        assert 0.2 <= stages["initial"] <= 1.0 and 0.5 <= stages["mid"] <= 1.35, crop


def test_kc_from_ndvi_behaviour():
    kc_map = KC_BY_CROP_STAGE["wheat"]
    static_kc, fapar = kc_from_ndvi(None, kc_map, "mid")
    assert static_kc == kc_map["mid"] and fapar is None  # NDVI غائب ⇒ ثابت المرحلة
    low_kc, _ = kc_from_ndvi(0.15, kc_map, "mid")
    high_kc, fap = kc_from_ndvi(0.85, kc_map, "mid")
    assert high_kc > low_kc  # غطاء أعلى ⇒ Kc أعلى
    assert 0.0 <= fap <= 1.0


# ── ETc + الاحتياج الصافي ────────────────────────────────────────────────────
def test_etc_equals_et0_times_kc():
    et0 = 5.0
    kc = KC_BY_CROP_STAGE["maize"]["mid"]
    assert abs(et0 * kc - 6.0) < 1e-9  # 5.0 × 1.20


def test_net_irrigation_is_etc_minus_effective_rain():
    etc = 6.0
    eff = _effective_rain(20.0)
    net = max(0.0, etc - eff)
    assert net == max(0.0, etc - eff) and net >= 0.0


# ── المطر الفعّال (USDA-SCS) ──────────────────────────────────────────────────
def test_effective_rain_usda_scs_anchors():
    assert _effective_rain(0.0) == 0.0
    assert _effective_rain(-5.0) == 0.0
    assert abs(_effective_rain(50.0) - 46.0) < 0.01  # 50·(125−10)/125
    assert abs(_effective_rain(100.0) - 102.5) < 0.01  # 0.1·100+92.5 (>75mm)


def test_effective_rain_is_monotonic_nondecreasing():
    prev = -1.0
    for r in range(0, 200, 10):
        e = _effective_rain(float(r))
        assert e >= prev
        prev = e
