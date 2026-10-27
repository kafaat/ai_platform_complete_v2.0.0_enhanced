"""Quantity evidence must remain distinct from task completion and ledger truth."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/sahool-platform"))

from api.irrigation_observations import IrrigationObservationInput  # noqa: E402

pytestmark = pytest.mark.unit


def observation(**changes):
    body = {
        "observation_id": str(uuid4()),
        "execution_id": str(uuid4()),
        "source": "farmer_task",
        "outcome": "irrigated",
        "occurred_at": datetime.now(UTC) - timedelta(minutes=1),
        "quantity_method": "unknown",
    }
    return IrrigationObservationInput.model_validate(body | changes)


def test_reported_meter_difference_is_not_verified_ledger_water():
    result = observation(
        quantity_method="meter",
        meter_start_m3=1200,
        meter_end_m3=4200,
        irrigated_area_ha=50,
    ).computed_quantity()
    assert result == {
        "volume_m3": 3000,
        "depth_mm": 6,
        "quality": "meter_observed",
        "ledger_eligible": False,
    }


def test_flow_is_integrated_over_active_time_not_full_elapsed_duration():
    result = observation(
        quantity_method="estimated_flow",
        flow_m3_h=390,
        duration_minutes=120,
        interruptions_minutes=30,
        irrigated_area_ha=50,
    ).computed_quantity()
    assert result["volume_m3"] == pytest.approx(585)
    assert result["depth_mm"] == pytest.approx(1.17)
    assert result["quality"] == "estimated_flow"
    assert result["ledger_eligible"] is False


def test_depth_is_unknown_without_actual_irrigated_area():
    result = observation(quantity_method="declared_volume", volume_m3=3000).computed_quantity()
    assert result["volume_m3"] == 3000
    assert result["depth_mm"] is None
    assert result["quality"] == "declared_volume"


@pytest.mark.parametrize("outcome", ["unknown", "not_irrigated", "irrigated"])
def test_absence_of_quantity_is_not_a_zero_measurement(outcome):
    result = observation(outcome=outcome).computed_quantity()
    assert result["volume_m3"] is None
    assert result["depth_mm"] is None
    assert result["ledger_eligible"] is False


def test_explicit_zero_report_is_distinct_from_unknown():
    result = observation(quantity_method="declared_volume", volume_m3=0).computed_quantity()
    assert result["volume_m3"] == 0
    assert result["quality"] == "declared_volume"


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity_method": "meter", "meter_start_m3": 10},
        {"quantity_method": "meter", "meter_start_m3": 10, "meter_end_m3": 9},
        {"quantity_method": "meter", "meter_start_m3": 10, "meter_end_m3": 11, "volume_m3": 1},
        {"quantity_method": "estimated_flow", "flow_m3_h": 100},
        {
            "quantity_method": "estimated_flow",
            "flow_m3_h": 100,
            "duration_minutes": 10,
            "interruptions_minutes": 10,
        },
        {
            "quantity_method": "estimated_flow",
            "flow_m3_h": 100,
            "duration_minutes": 10,
            "interruptions_minutes": 11,
        },
        {"quantity_method": "declared_volume"},
        {"quantity_method": "declared_volume", "volume_m3": 1, "interruptions_minutes": 1},
        {"quantity_method": "unknown", "volume_m3": 0},
        {"quantity_method": "unknown", "duration_minutes": 1},
        {"quantity_method": "unknown", "interruptions_minutes": 1},
    ],
)
def test_contradictory_or_incomplete_measurement_is_rejected(changes):
    with pytest.raises(ValidationError):
        observation(**changes)


@pytest.mark.parametrize("outcome", ["not_irrigated", "unknown"])
@pytest.mark.parametrize(
    "changes",
    [
        {"quantity_method": "declared_volume", "volume_m3": 0},
        {"irrigated_area_ha": 50},
    ],
)
def test_non_irrigated_outcomes_cannot_carry_quantity_evidence(outcome, changes):
    with pytest.raises(ValidationError):
        observation(outcome=outcome, **changes)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -1, True, "12"])
def test_nonphysical_or_coerced_volume_is_rejected(value):
    with pytest.raises(ValidationError):
        observation(quantity_method="declared_volume", volume_m3=value)


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity_method": "estimated_flow", "flow_m3_h": 0, "duration_minutes": 1},
        {"quantity_method": "estimated_flow", "flow_m3_h": 1, "duration_minutes": 0},
        {"quantity_method": "declared_volume", "volume_m3": 1, "irrigated_area_ha": 0},
        {"quantity_method": "declared_volume", "volume_m3": 1e308, "irrigated_area_ha": 1e-308},
        {"quantity_method": "estimated_flow", "flow_m3_h": 1e308, "duration_minutes": 1e308},
    ],
)
def test_invalid_denominators_and_computed_overflow_are_rejected(changes):
    with pytest.raises(ValidationError):
        observation(**changes)


def test_aware_timestamp_and_minimal_clock_skew():
    observation(occurred_at=datetime.now(UTC) + timedelta(seconds=20))
    with pytest.raises(ValidationError):
        observation(occurred_at=datetime.now(UTC) + timedelta(minutes=5))
    with pytest.raises(ValidationError):
        observation(occurred_at=datetime(2026, 1, 1))


@pytest.mark.parametrize(
    "changes",
    [
        {"observation_id": "bad-id"},
        {"execution_id": "bad-id"},
        {"source": "task_completion_ratio"},
        {"completion_ratio": 1},
        {"ledger_eligible": True},
        {"notes": "x" * 2001},
    ],
)
def test_identity_and_untrusted_promotions_are_rejected(changes):
    with pytest.raises(ValidationError):
        observation(**changes)


def test_json_roundtrip_preserves_observation_and_computed_quantity():
    report = observation(source="field_inspection", quantity_method="declared_volume", volume_m3=20)
    restored = IrrigationObservationInput.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.computed_quantity() == report.computed_quantity()
    with pytest.raises(ValidationError):
        report.volume_m3 = 999
