"""Synthetic catch-can evidence; no compliance threshold or measured farm claim."""

import pytest
from pydantic import ValidationError

from shared.precision_agriculture.irrigation_uniformity import UniformitySurvey, calculate_uniformity


def survey(depths, areas=None, pivot="a"):
    areas = areas if areas is not None else [1] * len(depths)
    return UniformitySurvey(
        evidence_ref=f"synthetic:180ha/pivot-{pivot}/catch-can-01",
        samples=[
            {"sample_id": str(i), "depth_mm": depth, "represented_area_m2": area}
            for i, (depth, area) in enumerate(zip(depths, areas, strict=True))
        ],
    )


def test_perfect_uniformity():
    result = calculate_uniformity(survey([10, 10, 10, 10]))
    assert result["mean_depth_mm"] == 10
    assert result["cu_pct"] == result["du_low_quarter_pct"] == 100
    assert result["evidence_ref"].startswith("synthetic:")
    assert result["compliance_status"] == "not_evaluated"


def test_equal_area_nonuniformity():
    result = calculate_uniformity(survey([4, 8, 12, 16]))
    assert result["mean_depth_mm"] == 10
    assert result["cu_pct"] == 60
    assert result["du_low_quarter_pct"] == 40


def test_area_weighted_fractional_quarter():
    result = calculate_uniformity(survey([2, 6, 10, 14], [1, 2, 3, 4]))
    assert result["mean_depth_mm"] == 10
    assert result["cu_pct"] == 68
    assert result["du_low_quarter_pct"] == 44


def test_zero_depths_not_evaluated():
    result = calculate_uniformity(survey([0, 0, 0, 0]))
    assert result["status"] == "not_evaluated"
    assert result["cu_pct"] is None and result["du_low_quarter_pct"] is None


@pytest.mark.parametrize("bad", [True, "10", -1, float("inf"), float("nan")])
def test_invalid_depth(bad):
    with pytest.raises(ValidationError):
        survey([1, 2, 3, bad])


@pytest.mark.parametrize("bad", [True, "1", 0, -1, float("inf"), float("nan")])
def test_invalid_area(bad):
    with pytest.raises(ValidationError):
        survey([1, 2, 3, 4], [1, 1, 1, bad])


def test_too_few_and_duplicate_ids():
    with pytest.raises(ValidationError):
        survey([1, 2, 3])
    data = survey([1, 2, 3, 4]).model_dump()
    data["samples"][1]["sample_id"] = data["samples"][0]["sample_id"]
    with pytest.raises(ValidationError):
        UniformitySurvey.model_validate(data)


def test_large_finite_depth_and_area():
    result = calculate_uniformity(survey([1e308] * 4, [1e308] * 4))
    assert result["mean_depth_mm"] == 1e308
    assert result["cu_pct"] == 100
    assert result["du_low_quarter_pct"] == 100


def test_synthetic_two_pivots_are_not_extrapolated_to_unsampled_area():
    a = calculate_uniformity(survey([4, 8, 12, 16], [125000] * 4))
    b = calculate_uniformity(survey([8, 8, 8, 8], [125000] * 4, pivot="b"))
    assert a["du_low_quarter_pct"] == 40
    assert b["du_low_quarter_pct"] == 100
    assert a["evidence_ref"] != b["evidence_ref"]
    assert 180 - 50 - 50 == 80  # Remaining land has no survey in the fixture.
