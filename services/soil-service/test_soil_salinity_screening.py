import pytest
from p2_products import build_salinity_assessment
from pydantic import ValidationError

from shared.contracts.soil.p2 import SalinityAssessmentRequest, SalinityZoneEvidence


def assess(**readings):
    zone = SalinityZoneEvidence(
        zone_id="pivot",
        salinity_index=0,
        brightness=0,
        gypsum_index=0,
        carbonate_index=0,
        persistence=0,
        drainage_risk=0,
        **readings,
    )
    request = SalinityAssessmentRequest(
        tenant_id="t", field_id="f", geometry_hash="g", zones=[zone]
    )
    return build_salinity_assessment(request).zones[0]


@pytest.mark.parametrize(
    ("ece", "esp", "label"),
    [
        (4, 15, "saline_sodic_candidate"),
        (12, 22, "saline_sodic_candidate"),
        (4, 14.9, "saline_candidate"),
        (3.9, 15, "sodic_candidate"),
        (3.9, 14.9, "low_signal"),
    ],
)
def test_reported_saturation_extract_and_esp_in_low_reflectance(ece, esp, label):
    result = assess(ec_lab_ds_m=ece, ec_lab_method="saturation_extract_25c", esp_pct=esp)
    assert result.classification == label
    assert result.evidence_level == "screening"
    assert result.allowed_use == ["screening", "sampling_priority"]
    assert set(result.blocked_use) == {
        "gypsum_rate",
        "leaching_requirement",
        "reclamation_execution",
    }


@pytest.mark.parametrize("method", [None, "other", "soil_water_1_1", "soil_water_1_5"])
def test_unknown_or_dilute_extract_is_not_treated_as_ece(method):
    result = assess(ec_lab_ds_m=12, ec_lab_method=method, esp_pct=22)
    assert result.classification == "sodic_candidate"
    assert "soil_ec_not_comparable_to_saturation_extract_25c" in result.evidence_notes
    assert result.salinity_probability == assess(esp_pct=22).salinity_probability


@pytest.mark.parametrize(
    "readings",
    [
        {"ec_lab_ds_m": -3},
        {"esp_pct": -4},
        {"esp_pct": 101},
        {"sar": -1},
        {"ecw_ds_m": -1},
        {"ec_lab_ds_m": float("nan")},
        {"sar": float("inf")},
    ],
)
def test_nonphysical_chemistry_is_rejected(readings):
    with pytest.raises(ValidationError):
        assess(**readings)
