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

import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


# ── Growth stages (FAO-56 Ch.6) ──────────────────────────────────────
class GrowthStage(str, Enum):
    INITIAL = "initial"           # planting -> ~10% ground cover
    DEVELOPMENT = "development"   # 10% cover -> effective full cover
    MID_SEASON = "mid_season"     # full cover -> start of maturity
    LATE_SEASON = "late_season"   # maturity -> harvest


@dataclass
class WeatherDay:
    """Daily weather inputs for ET0. All from weather-service."""
    temp_max_c: float
    temp_min_c: float
    humidity_pct: float            # mean relative humidity
    wind_speed_m_s: float          # at 2m height
    solar_radiation_mj_m2: float   # MJ/m2/day
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
    salt_tolerance_ece: float      # EC threshold dS/m (FAO-56 Table 23)
    salt_slope_pct: float          # % yield loss per dS/m above threshold
    source: str = "FAO-56 Table 11/12/23"

    @property
    def total_season_days(self) -> int:
        return sum(self.stage_days)


# ── ET0: Penman-Monteith (FAO-56 Eq. 6) ──────────────────────────────
def penman_monteith_et0(w: WeatherDay) -> float:
    """Reference evapotranspiration (mm/day) via FAO-56 Penman-Monteith.

    This is the VARIABLE — recomputed every day from weather.
    Returns ET0 in mm/day.
    """
    # Atmospheric pressure (kPa) from elevation — FAO-56 Eq. 7
    P = 101.3 * ((293.0 - 0.0065 * w.elevation_m) / 293.0) ** 5.26
    # Psychrometric constant (kPa/°C) — FAO-56 Eq. 8
    gamma = 0.000665 * P

    # Saturation vapour pressure (kPa) — FAO-56 Eq. 11/12
    def es_t(t: float) -> float:
        return 0.6108 * math.exp((17.27 * t) / (t + 237.3))

    es = (es_t(w.temp_max_c) + es_t(w.temp_min_c)) / 2.0
    ea = es * (w.humidity_pct / 100.0)  # actual vapour pressure

    # Slope of vapour pressure curve (kPa/°C) — FAO-56 Eq. 13
    delta = (4098.0 * es_t(w.temp_mean_c)) / ((w.temp_mean_c + 237.3) ** 2)

    # Net radiation estimate (simplified; full version uses Rs/Rso)
    # Rn ~ 0.77 * Rs (albedo 0.23) minus net longwave (FAO-56 Eq. 38-40)
    lat_rad = math.radians(w.latitude_deg)
    dr = 1.0 + 0.033 * math.cos(2 * math.pi * w.day_of_year / 365.0)
    decl = 0.409 * math.sin(2 * math.pi * w.day_of_year / 365.0 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(lat_rad) * math.tan(decl))))
    ra = (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(lat_rad) * math.sin(decl)
        + math.cos(lat_rad) * math.cos(decl) * math.sin(ws)
    )
    rso = (0.75 + 2e-5 * w.elevation_m) * ra
    rs = w.solar_radiation_mj_m2
    rns = 0.77 * rs
    # Net longwave (FAO-56 Eq. 39)
    sigma = 4.903e-9
    tmaxk = w.temp_max_c + 273.16
    tmink = w.temp_min_c + 273.16
    rs_rso = min(1.0, rs / rso) if rso > 0 else 0.5
    rnl = sigma * ((tmaxk ** 4 + tmink ** 4) / 2.0) * (
        0.34 - 0.14 * math.sqrt(ea)
    ) * (1.35 * rs_rso - 0.35)
    rn = rns - rnl

    # Soil heat flux (daily ~ 0)
    g = 0.0

    # FAO-56 Penman-Monteith — Eq. 6
    numerator = (
        0.408 * delta * (rn - g)
        + gamma * (900.0 / (w.temp_mean_c + 273.0)) * w.wind_speed_m_s * (es - ea)
    )
    denominator = delta + gamma * (1.0 + 0.34 * w.wind_speed_m_s)
    et0 = numerator / denominator
    return max(0.0, et0)


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
    texture: str                   # sandy | loam | clay | mixed
    taw_mm_per_m: float            # total available water
    raw_fraction: float            # readily available fraction (p)
    ke_factor: float               # surface evaporation multiplier
    drainage: str                  # fast | medium | slow
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
) -> IrrigationResult:
    """Full FAO-56 chain for ONE zone on ONE day.

    Run this per-zone to produce a Variable-Rate Irrigation (VRA) map.
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

    # 5. salinity stress
    ks = salinity_stress_ks(crop, soil_ece)
    etc_adj = etc_zone * ks
    if ks < 1.0:
        notes.append(
            f"إجهاد ملحي: EC={soil_ece} يتجاوز عتبة {crop.salt_tolerance_ece} "
            f"(Ks={ks:.2f})"
        )

    # 6. net irrigation (minus effective rainfall)
    net = max(0.0, etc_adj - effective_rainfall_mm)

    # 7. leaching + efficiency -> gross
    lr = leaching_requirement(water_ec, crop.salt_tolerance_ece)
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
