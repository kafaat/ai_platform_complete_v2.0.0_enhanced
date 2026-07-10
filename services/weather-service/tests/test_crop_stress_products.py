from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chill_accumulation import compute_chill_accumulation  # noqa: E402
from lodging_risk import compute_lodging_risk  # noqa: E402
from pollination_risk import compute_pollination_risk  # noqa: E402

pytestmark = pytest.mark.unit


# ── lodging ──
def test_lodging_unknown_crop_fails_closed():
    out = compute_lodging_risk(crop="unicorn", stage="heading", max_wind_gust_mps=25)
    assert out["status"] == "insufficient_context"
    assert out["risk"] is None and out["evidence_role"] == "supporting"


def test_lodging_no_wind_fails_closed():
    out = compute_lodging_risk(crop="wheat", stage="grain_filling", max_wind_gust_mps=None)
    assert out["status"] == "insufficient_context"
    assert "no_wind_forecast" in out["limiting_factors"]


def test_lodging_high_gust_susceptible_stage_is_high():
    out = compute_lodging_risk(
        crop="barley", stage="grain_filling", max_wind_gust_mps=22.0, forecast_rain_mm=25.0
    )
    assert out["status"] == "ok"
    assert out["risk"] == "high"
    assert out["wet_soil"] is True
    assert "wet_soil_weak_anchorage" in out["limiting_factors"]


def test_lodging_low_wind_short_crop_is_low_or_none():
    out = compute_lodging_risk(crop="sorghum", stage="vegetative", max_wind_gust_mps=9.0)
    assert out["risk"] in {"none", "low"}


# ── pollination ──
def test_pollination_outside_flowering_is_not_applicable():
    out = compute_pollination_risk(crop="maize", stage="vegetative", day_max_c=40, night_min_c=5)
    assert out["status"] == "not_applicable"  # صدق: لا خطر على تلقيح غير جارٍ
    assert out["risk"] is None


def test_pollination_unknown_crop_fails_closed():
    out = compute_pollination_risk(crop="unicorn", stage="flowering", day_max_c=40, night_min_c=5)
    assert out["status"] == "insufficient_context"


def test_pollination_heat_during_silking_is_high():
    out = compute_pollination_risk(crop="maize", stage="silking", day_max_c=42.0, night_min_c=20.0)
    assert out["status"] == "ok"
    assert out["risk"] == "high"
    assert "pollen_sterility_heat" in out["limiting_factors"]


def test_pollination_frost_forces_high():
    out = compute_pollination_risk(crop="almond", stage="bloom", day_max_c=12.0, night_min_c=-2.0)
    assert out["risk"] == "high"
    assert "frost_flower_kill" in out["limiting_factors"]


# ── chill ──
def test_chill_non_perennial_is_not_applicable():
    out = compute_chill_accumulation(crop="wheat", hourly_temp_c=[5] * 100)
    assert out["status"] == "not_applicable"


def test_chill_no_series_fails_closed():
    out = compute_chill_accumulation(crop="almond", hourly_temp_c=[])
    assert out["status"] == "insufficient_context"


def test_chill_counts_hours_and_utah_units_and_pct():
    # 400 ساعة عند 5°م: كلّها ضمن نطاق التبريد (0..7.2) وUtah=1 لكلٍّ.
    out = compute_chill_accumulation(crop="almond", hourly_temp_c=[5.0] * 400)
    assert out["status"] == "ok"
    assert out["chilling_hours"] == 400
    assert out["utah_chill_units"] == 400.0
    assert out["requirement_hours"] == 300.0
    assert out["requirement_met"] is True  # 400 >= 300
    assert out["requirement_met_pct"] == 100.0  # مقصوص عند 100


def test_chill_dynamic_model_declared_not_faked():
    out = compute_chill_accumulation(crop="grape", hourly_temp_c=[4.0] * 50)
    assert out["provenance"]["dynamic_model"] == "not_implemented"  # صدق


def test_chill_warm_hours_do_not_accumulate():
    out = compute_chill_accumulation(crop="apple", hourly_temp_c=[25.0] * 100)
    assert out["chilling_hours"] == 0
    assert out["utah_chill_units"] == 0.0  # لا رصيد سالب مُبلَّغ
