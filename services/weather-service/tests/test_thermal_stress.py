from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from thermal_stress import (  # noqa: E402
    PRODUCT_ID,
    compute_compound_thermal_stress,
    resolve_thresholds,
)

pytestmark = pytest.mark.unit


def test_unknown_crop_fails_closed_no_fabricated_risk():
    out = compute_compound_thermal_stress(
        crop="unicorn_fruit", stage="flowering", daily_max_c=[39], daily_min_c=[7]
    )
    assert out["status"] == "insufficient_context"
    assert out["risk"] is None  # لا مخاطرة مُختلَقة
    assert out["evidence_role"] == "supporting"
    assert "unknown_crop_or_stage" in out["limiting_factors"]


def test_missing_series_fails_closed():
    out = compute_compound_thermal_stress(
        crop="wheat", stage="flowering", daily_max_c=[], daily_min_c=[]
    )
    assert out["status"] == "insufficient_context"
    assert out["risk"] is None


def test_extreme_day_heat_cold_night_flowering_is_high():
    # نهار 39 / ليل 7 على قمح مُزهِر: حرّ فوق عتبة الإزهار (26) + تباين كبير ⇒ high.
    out = compute_compound_thermal_stress(
        crop="wheat", stage="flowering", daily_max_c=[39.0], daily_min_c=[7.0]
    )
    assert out["status"] == "ok"
    assert out["risk"] == "high"
    assert out["max_diurnal_range_c"] == 32.0
    assert "extreme_daytime_heat" in out["limiting_factors"]
    assert "sensitive_reproductive_stage" in out["limiting_factors"]
    assert out["evidence_role"] == "supporting"  # لا يحجب القرار قبل المعايرة
    assert 0.0 < out["confidence"] <= 0.85  # ثقة صريحة مُصدَرة


def test_mild_swing_is_low_or_none():
    # نهار 34 / ليل 19 على قمح خضريّ: تحت العتبات ⇒ لا إجهاد.
    out = compute_compound_thermal_stress(
        crop="wheat", stage="vegetative", daily_max_c=[28.0], daily_min_c=[19.0]
    )
    assert out["status"] == "ok"
    assert out["risk"] in {"none", "low"}


def test_frost_nights_force_high_and_flag():
    out = compute_compound_thermal_stress(
        crop="tomato", stage="flowering", daily_max_c=[22.0], daily_min_c=[1.0]
    )
    assert out["risk"] == "high"
    assert out["frost_nights"] == 1
    assert "frost_risk" in out["limiting_factors"]


def test_consecutive_cold_nights_counted():
    out = compute_compound_thermal_stress(
        crop="pepper",
        stage="vegetative",
        daily_max_c=[25, 24, 23],
        daily_min_c=[8, 9, 20],  # ليلتان باردتان متتاليتان (< 12) ثمّ دافئة
    )
    assert out["consecutive_cold_nights"] == 2
    assert out["cold_stress_nights"] == 2


def test_hourly_series_yields_honest_stress_hours():
    out = compute_compound_thermal_stress(
        crop="wheat",
        stage="grain_filling",
        daily_max_c=[35.0],
        daily_min_c=[3.0],
        hourly_temp_c=[36, 37, 2, 1, 20],
        hourly_is_daytime=[1, 1, 0, 0, 1],
        hourly_rh_pct=[40, 45, 95, 92, 60],
    )
    assert out["provenance"]["temporal_resolution"] == "hourly"
    assert out["day_heat_stress_hours"] == 2  # 36,37 نهاراً فوق 28
    assert out["night_cold_stress_hours"] == 2  # 2,1 ليلاً تحت 4
    assert out["dew_leaf_wetness_estimate_hours"] == 2  # RH>=90 ساعتان


def test_daily_only_declares_requires_hourly():
    out = compute_compound_thermal_stress(
        crop="wheat", stage="mid", daily_max_c=[31.0], daily_min_c=[10.0]
    )
    assert out.get("hours_note") == "requires_hourly_series"
    assert "day_heat_stress_hours" not in out  # لا اختلاق ساعات


def test_resolve_thresholds_stage_override():
    base = resolve_thresholds("wheat", None)
    flower = resolve_thresholds("wheat", "flowering")
    assert base is not None and flower is not None
    assert flower["heat_c"] < base["heat_c"]  # الإزهار أشدّ حساسيّة للحرّ
    assert resolve_thresholds("unknown", "x") is None


def test_product_identity_and_honesty_metadata():
    out = compute_compound_thermal_stress(
        crop="grape", stage="flowering", daily_max_c=[36.0], daily_min_c=[8.0]
    )
    assert out["provenance"]["product"] == PRODUCT_ID
    assert out["provenance"]["leaf_wetness"] == "estimated_not_measured"
