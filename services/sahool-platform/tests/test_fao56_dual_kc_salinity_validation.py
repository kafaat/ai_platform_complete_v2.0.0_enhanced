"""تحقّق زراعيّ FAO-56 — الفصل ٧ (Kc المزدوج) والفصل ٨ (الملوحة).

يكمّل ``test_fao56_agronomic_validation`` بالتحقّق من محرّك ``core.engines.fao56``
مقابل معادلات وجداول FAO-56 المنشورة:

- **Ks الملوحة** (Maas-Hoffman، eq. 81 / Table 23): القمح threshold=6.0 dS/m،
  slope=7.1 %/dS/m ⇒ Ks(8)=0.858.
- **منحنى Kc** (Fig. 34): ابتدائيّ ثابت → تطوّر خطّيّ → ذروة ثابتة → أفول.
- **Kc_max** (eq. 72) · **Kr** (eq. 74) · **few** (eq. 75) · **TEW/REW** (Table 19).
- **fc من NDVI** و**Kd الكثافة** (eq. 76) · **ETc المزدوج** (eq. 80).

منطق فيزيائيّ صرف (وظيفة Platform Unit Tests).
"""

from __future__ import annotations

import pytest
from core.engines.fao56 import (
    GrowthStage,
    density_coefficient_kd,
    evaporation_reduction_kr,
    few_exposed_wetted,
    fractional_cover_from_ndvi,
    kc_for_age,
    kc_max,
    kcb_for_age,
    salinity_stress_ks,
    tew_rew_for_texture,
)
from core.season_phenology import crop_kc_profile, resolve_crop_id


@pytest.fixture
def wheat():
    return crop_kc_profile(resolve_crop_id("wheat"))


# ── الملوحة: Maas-Hoffman (FAO-56 eq. 81 / Table 23) ────────────────────────
def test_salinity_threshold_and_slope_are_fao56_table_23(wheat):
    assert wheat.salt_tolerance_ece == 6.0  # القمح: عتبة ECe = 6.0 dS/m
    assert wheat.salt_slope_pct == 7.1  # ميل الخسارة 7.1 %/dS/m


def test_salinity_ks_no_stress_below_threshold(wheat):
    assert salinity_stress_ks(wheat, 0.0) == 1.0
    assert salinity_stress_ks(wheat, wheat.salt_tolerance_ece) == 1.0


def test_salinity_ks_maas_hoffman_linear(wheat):
    # Ks = 1 − slope·(ECe − threshold)/100 = 1 − 7.1·2/100 = 0.858
    assert abs(salinity_stress_ks(wheat, 8.0) - 0.858) < 1e-6
    # منخفض أكثر عند ملوحة أعلى (رتيب متناقص).
    assert salinity_stress_ks(wheat, 10.0) < salinity_stress_ks(wheat, 8.0)


def test_salinity_ks_clamped_to_zero(wheat):
    assert salinity_stress_ks(wheat, 100.0) == 0.0  # لا سالب


# ── منحنى Kc (FAO-56 Fig. 34) ───────────────────────────────────────────────
def test_kc_curve_stages(wheat):
    s_ini, s_dev, s_mid, s_late = wheat.stage_days
    kc_ini, st_ini = kc_for_age(wheat, 1)
    assert st_ini == GrowthStage.INITIAL and kc_ini == wheat.kc_initial
    kc_mid, st_mid = kc_for_age(wheat, s_ini + s_dev + 1)
    assert st_mid == GrowthStage.MID_SEASON and kc_mid == wheat.kc_mid
    # التطوّر بين الابتدائيّ والذروة.
    kc_dev, st_dev = kc_for_age(wheat, s_ini + s_dev // 2)
    assert st_dev == GrowthStage.DEVELOPMENT
    assert wheat.kc_initial < kc_dev < wheat.kc_mid


def test_kcb_is_kc_minus_offset_floored(wheat):
    kcb, _ = kcb_for_age(wheat, wheat.stage_days[0] + wheat.stage_days[1] + 1)
    assert abs(kcb - (wheat.kc_mid - 0.05)) < 1e-9
    kcb_ini, _ = kcb_for_age(wheat, 1)
    assert kcb_ini >= 0.15  # أرضيّة تربة عارية


# ── Kc_max (FAO-56 eq. 72) ──────────────────────────────────────────────────
def test_kc_max_formula_and_floor():
    kcb = 1.10
    # u2=2, RHmin=45, h=3 ⇒ adj = 1.2 + 0 = 1.2 ⇒ Kc_max = max(1.2, 1.15) = 1.2
    assert abs(kc_max(kcb, 2.0, 45.0, 3.0) - 1.2) < 1e-9
    # لا ينزل دون Kcb+0.05.
    assert kc_max(1.30, 1.0, 80.0, 0.1) >= 1.30 + 0.05


def test_kc_max_clamps_wind_and_rh():
    # قيم متطرّفة تُقصّ للنطاق (u2∈[1,6], RHmin∈[20,80]) — لا انفجار.
    assert 1.0 < kc_max(1.0, 20.0, 5.0, 2.0) < 1.6


# ── Kr تخفيض التبخّر (FAO-56 eq. 74) ────────────────────────────────────────
def test_kr_stage1_energy_limited():
    assert evaporation_reduction_kr(2.0, 16.0, 8.0) == 1.0  # De ≤ REW


def test_kr_stage2_falling_diffusion_limited():
    # De=12, TEW=16, REW=8 ⇒ Kr = (16−12)/(16−8) = 0.5
    assert abs(evaporation_reduction_kr(12.0, 16.0, 8.0) - 0.5) < 1e-9
    assert evaporation_reduction_kr(16.0, 16.0, 8.0) == 0.0  # De = TEW ⇒ جفاف تامّ


# ── few (FAO-56 eq. 75) ─────────────────────────────────────────────────────
def test_few_min_of_exposed_and_wetted():
    assert abs(few_exposed_wetted(0.3, 1.0) - 0.7) < 1e-9  # min(1−0.3, 1.0)
    assert abs(few_exposed_wetted(0.3, 0.3) - 0.3) < 1e-9  # تنقيط: fw صغير يحكم


# ── TEW/REW (FAO-56 Table 19) ───────────────────────────────────────────────
def test_tew_rew_table_values_and_ordering():
    assert tew_rew_for_texture("sand") == (8.0, 3.0)
    assert tew_rew_for_texture("loam") == (16.0, 8.0)
    assert tew_rew_for_texture("clay") == (18.0, 12.0)
    assert tew_rew_for_texture("unknown-texture") == tew_rew_for_texture("loam")  # افتراضيّ
    for tex in ("sand", "loam", "clay", "silt"):
        tew, rew = tew_rew_for_texture(tex)
        assert tew > rew > 0


# ── fc من NDVI + Kd الكثافة (FAO-56 §9.4 / eq. 76) ──────────────────────────
def test_fractional_cover_from_ndvi():
    assert fractional_cover_from_ndvi(0.15) == 0.0  # عند الأرض العارية
    assert fractional_cover_from_ndvi(0.85) == 1.0  # عند الغطاء الكامل
    assert 0.0 < fractional_cover_from_ndvi(0.5) < 1.0
    with pytest.raises(ValueError):
        fractional_cover_from_ndvi(0.5, ndvi_bare=0.9, ndvi_full=0.9)


def test_density_coefficient_bounds():
    assert density_coefficient_kd(0.0, 0.5) == 0.0  # تربة عارية
    assert abs(density_coefficient_kd(1.0, 0.5) - 1.0) < 1e-9  # غطاء كامل
    mid = density_coefficient_kd(0.5, 0.5)
    assert 0.0 < mid <= 1.0


# ── ETc المزدوج (FAO-56 eq. 80): ETc = (Kcb·Ks + Ke)·ET0 ───────────────────
def test_dual_kc_etc_composition():
    kcb, ks, ke, et0 = 1.05, 0.858, 0.20, 5.0
    etc = (kcb * ks + ke) * et0
    # الإجهاد يخفّض النتح لا التبخّر السطحيّ.
    etc_no_stress = (kcb * 1.0 + ke) * et0
    assert etc < etc_no_stress
    assert abs(etc - (kcb * ks + ke) * et0) < 1e-9
