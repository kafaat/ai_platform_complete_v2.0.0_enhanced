"""Reject non-finite drainage and reclamation inputs at the shared boundary."""

import pytest
from pydantic import ValidationError

from shared.contracts.soil.p3 import (
    DrainageAssessmentRequest,
    ReclamationAssessmentRequest,
    ReclamationEconomicsRequest,
)

_DRAINAGE = dict(
    tenant_id="t",
    field_id="f",
    geometry_hash="g",
    natural_outlet_score=0.8,
    depression_fraction=0.1,
    mean_drainage_gradient_pct=0.5,
    flood_risk=0.1,
    wadi_risk=0.1,
    salinity_persistence=0.1,
)
_RECLAMATION = dict(
    tenant_id="t",
    field_id="f",
    geometry_hash="g",
    salinity_probability=0.5,
    sodicity_probability=0.5,
    gypsum_probability=0.5,
    stoniness_fraction=0.1,
    compaction_risk=0.1,
    leveling_need=0.1,
    drainage_need="monitor",
    crop_suitability_score=0.8,
)
_ECONOMICS = dict(
    tenant_id="t",
    field_id="f",
    area_ha=10,
    water_cost_per_m3=0.2,
    energy_cost_per_kwh=0.3,
    gypsum_cost_per_tonne=100,
    drainage_cost_per_ha=1000,
    leveling_cost_per_ha=200,
    stone_removal_cost_per_ha=100,
    expected_annual_margin_per_ha=500,
)


@pytest.mark.parametrize(
    "field",
    [
        "water_table_depth_m",
        "impermeable_layer_depth_m",
        "mean_drainage_gradient_pct",
        "ksat_mm_h",
    ],
)
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_drainage_rejects_nonfinite_measurements(field, value):
    with pytest.raises(ValidationError) as exc:
        DrainageAssessmentRequest(**(_DRAINAGE | {field: value}))
    assert exc.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["ec_lab_ds_m", "esp_pct"])
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_reclamation_rejects_nonfinite_lab_measurements(field, value):
    with pytest.raises(ValidationError) as exc:
        ReclamationAssessmentRequest(**(_RECLAMATION | {field: value}))
    assert exc.value.errors()[0]["loc"] == (field,)


def test_esp_cannot_exceed_one_hundred_percent():
    with pytest.raises(ValidationError):
        ReclamationAssessmentRequest(**_RECLAMATION, esp_pct=100.01)


@pytest.mark.parametrize(
    "field",
    [
        "area_ha",
        "water_cost_per_m3",
        "energy_cost_per_kwh",
        "gypsum_cost_per_tonne",
        "drainage_cost_per_ha",
        "leveling_cost_per_ha",
        "stone_removal_cost_per_ha",
        "expected_annual_margin_per_ha",
        "water_m3_per_ha",
        "energy_kwh_per_ha",
        "gypsum_t_per_ha",
    ],
)
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_reclamation_economics_rejects_nonfinite_inputs(field, value):
    with pytest.raises(ValidationError) as exc:
        ReclamationEconomicsRequest(**(_ECONOMICS | {field: value}))
    assert exc.value.errors()[0]["loc"] == (field,)


def test_unknown_drainage_measurements_remain_unknown():
    req = DrainageAssessmentRequest(**_DRAINAGE)
    assert req.water_table_depth_m is None
    assert req.impermeable_layer_depth_m is None
    assert req.ksat_mm_h is None


def test_valid_zero_and_percentage_boundary_are_preserved():
    req = ReclamationAssessmentRequest(**_RECLAMATION, ec_lab_ds_m=0, esp_pct=100)
    assert req.ec_lab_ds_m == 0
    assert req.esp_pct == 100
    assert ReclamationAssessmentRequest(**_RECLAMATION).esp_pct is None


def test_valid_economic_inputs_and_defaults_are_preserved():
    req = ReclamationEconomicsRequest(**_ECONOMICS)
    assert req.area_ha == 10
    assert req.water_cost_per_m3 == 0.2
    assert req.water_m3_per_ha == 0
    assert req.energy_kwh_per_ha == 0
    assert req.gypsum_t_per_ha == 0
