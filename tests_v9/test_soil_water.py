"""اختبار خصائص ماء التربة حسب النسيج (FAO-56 Table 19، #374) — نقيّ حتميّ.

يثبت: (أ) TAW = TAW(نسيج)×عمق؛ (ب) RAW = p×TAW؛ (ج) مفاتيح عربيّة/إنجليزيّة؛
(د) نسيج مجهول ⇒ احتياطيّ + texture_known=False + تحذير؛ (هـ) عمق غائب ⇒ افتراض
موسوم؛ (و) p مقصوص [0,1]؛ (ز) calibrated=False؛ (ح) رمل < طمي < (TAW). نواة بلا شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.soil_water import (  # noqa: E402
    available_water_fraction,
    irrigation_due_by_soil,
    soil_water_params,
)


def test_taw_is_per_m_times_depth():
    # loam = 175 مم/م × 1.0 م = 175.
    r = soil_water_params("loam", root_depth_m=1.0)
    assert r["taw_mm_per_m"] == 175.0
    assert r["taw_mm"] == pytest.approx(175.0)
    assert r["texture_known"] is True


def test_raw_is_p_times_taw():
    r = soil_water_params("loam", root_depth_m=1.0, raw_fraction=0.4)
    assert r["raw_mm"] == pytest.approx(0.4 * 175.0)
    assert r["raw_fraction"] == 0.4


def test_arabic_texture_keys():
    assert soil_water_params("رملي", 1.0)["taw_mm_per_m"] == 65.0  # sand
    assert soil_water_params("طيني", 1.0)["taw_mm_per_m"] == 135.0  # clay
    assert soil_water_params("طميي", 1.0)["taw_mm_per_m"] == 175.0  # loam


def test_unknown_texture_fallback_flagged():
    r = soil_water_params("moon_dust", 1.0)
    assert r["texture_known"] is False
    assert r["taw_mm_per_m"] == 150.0
    assert any("نسيج غير معروف" in w for w in r["warnings_ar"])


def test_missing_depth_defaults_flagged():
    r = soil_water_params("loam", None)
    assert r["root_depth_m"] == 0.6
    assert any("عمق الجذور غائب" in w for w in r["warnings_ar"])
    r2 = soil_water_params("loam", -1.0)  # عمق غير صالح ⇒ نفس الافتراض
    assert r2["root_depth_m"] == 0.6


def test_p_clamped():
    assert soil_water_params("loam", 1.0, raw_fraction=2.0)["raw_fraction"] == 1.0
    assert soil_water_params("loam", 1.0, raw_fraction=-0.5)["raw_fraction"] == 0.0


def test_calibrated_false():
    assert soil_water_params("loam", 1.0)["calibrated"] is False


def test_sand_holds_less_than_clay_than_loam():
    sand = soil_water_params("sand", 1.0)["taw_mm"]
    clay = soil_water_params("clay", 1.0)["taw_mm"]
    loam = soil_water_params("loam", 1.0)["taw_mm"]
    assert sand < clay < loam  # 65 < 135 < 175 (FAO-56 Table 19)


def test_available_water_fraction_bounds():
    assert available_water_fraction(0.0, 100.0) == 1.0  # ممتلئة
    assert available_water_fraction(100.0, 100.0) == 0.0  # ذبول
    assert available_water_fraction(40.0, 100.0) == pytest.approx(0.6)
    assert available_water_fraction(200.0, 100.0) == 0.0  # مقصوص
    assert available_water_fraction(10.0, 0.0) == 0.0  # TAW صفر آمن


def test_soil_aware_timing_sand_before_clay():
    # نقطة المستخدم: نفس Dr (نفس ETc) ⇒ الرمل يستحقّ الريّ قبل الطين.
    sand = soil_water_params("sand", 1.0)  # TAW=65 ⇒ RAW=32.5
    clay = soil_water_params("clay", 1.0)  # TAW=135 ⇒ RAW=67.5
    dr = 40.0
    assert irrigation_due_by_soil(dr, sand["taw_mm"], sand["raw_fraction"]) is True
    assert irrigation_due_by_soil(dr, clay["taw_mm"], clay["raw_fraction"]) is False
    # القرار من كسر الماء المتاح لا ETc وحده.
    assert available_water_fraction(dr, sand["taw_mm"]) < available_water_fraction(
        dr, clay["taw_mm"]
    )


def test_irrigation_due_equivalent_to_dr_ge_raw():
    sp = soil_water_params("loam", 1.0, raw_fraction=0.5)  # RAW=87.5
    assert irrigation_due_by_soil(sp["raw_mm"], sp["taw_mm"], sp["raw_fraction"]) is True
    assert irrigation_due_by_soil(sp["raw_mm"] - 1.0, sp["taw_mm"], sp["raw_fraction"]) is False


def test_feeds_root_zone_balance():
    # تكامل: مخرجات soil_water تُغذّي root_zone_balance مباشرةً.
    from api.root_zone_balance import DayInput, root_zone_balance

    sp = soil_water_params("sandy_loam", root_depth_m=0.8, raw_fraction=0.5)
    rz = root_zone_balance(
        [DayInput(et0_mm=10.0, kc=1.0) for _ in range(20)],
        taw_mm=sp["taw_mm"],
        raw_fraction=sp["raw_fraction"],
    )
    assert rz.taw_mm == pytest.approx(sp["taw_mm"])
    assert rz.raw_mm == pytest.approx(sp["raw_mm"])
