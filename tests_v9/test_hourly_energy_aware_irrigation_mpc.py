import sys
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1] / "services" / "sahool-platform" / "api"
sys.path.insert(0, str(API))

from hourly_energy_aware_irrigation_mpc import solve_hourly_energy_aware_mpc  # noqa: E402

H = "a" * 64
NOW = datetime(2026, 7, 13, 6, tzinfo=UTC)


def water(dr=70.0, eligible=True):
    return {
        "operational_eligible": eligible,
        "taw_mm": 120.0,
        "raw_mm": 60.0,
        "depletion_mm": dr,
        "water_state_digest": H,
        "weather_snapshot_digest": "b" * 64,
        "soil_profile_digest": "c" * 64,
        "season_state_digest": "d" * 64,
    }


def capability():
    return {
        "status": "verified",
        "maximum_flow_lps": 50.0,
        "maximum_daily_depth_mm": 15.0,
        "maximum_safe_depth_mm_event": 10.0,
        "specific_energy_kwh_m3": 0.3,
        "pump_starting_kva": 25.0,
        "required_energy_load_ids": ["pump-1", "pivot-1"],
        "irrigation_capability_digest": "e" * 64,
    }


def gate(executable=True):
    return {
        "status": "executable" if executable else "blocked",
        "execution_allowed": executable,
        "executability_digest": "f" * 64,
    }


def forecast(hours=24, power=100.0, cost=0.2):
    rows = []
    for i in range(hours):
        rows.append(
            {
                "hour": (NOW + timedelta(hours=i)).isoformat(),
                "etc_mm": 0.2,
                "effective_rain_mm": 0.0,
                "maximum_available_power_kw": power,
                "maximum_starting_kva": 100.0,
                "energy_cost_per_kwh": cost + (0.1 if i < 4 else 0.0),
                "renewable_fraction": 0.8 if 6 <= i <= 16 else 0.2,
                "permitted_load_ids": ["pump-1", "pivot-1"],
                "energy_window_digest": str(i % 10) * 64,
            }
        )
    return rows


def solve(**kwargs):
    params = dict(
        tenant_id="tenant-1",
        field_id="field-1",
        season_id="season-1",
        canonical_water_state=water(),
        irrigation_capability=capability(),
        commissioning_gate=gate(),
        hourly_forecast=forecast(),
        area_ha=50.0,
    )
    params.update(kwargs)
    return solve_hourly_energy_aware_mpc(**params)


def test_builds_hourly_recommendation_only_schedule():
    result = solve()
    assert result.status in {"verified", "degraded"}
    assert result.decision == "irrigate"
    assert result.execution_allowed is False
    assert result.recommendation_only is True
    assert result.actions
    assert len(result.schedule_digest) == 64
    assert result.objectives["j2_total_energy_kwh"] > 0


def test_commissioning_gate_blocks():
    result = solve(commissioning_gate=gate(False))
    assert result.status == "blocked"
    assert "COMMISSIONING_EXECUTABILITY_GATE_REQUIRED" in result.blocking_reasons


def test_non_operational_water_state_blocks():
    result = solve(canonical_water_state=water(eligible=False))
    assert "CANONICAL_WATER_STATE_NOT_OPERATIONAL" in result.blocking_reasons


def test_no_energy_window_blocks():
    result = solve(hourly_forecast=forecast(power=1.0))
    assert result.status == "blocked"
    assert "NO_FEASIBLE_HOURLY_ENERGY_WINDOW" in result.blocking_reasons


def test_hold_when_refill_not_needed():
    result = solve(canonical_water_state=water(dr=10.0), hourly_forecast=forecast(hours=4))
    assert result.decision == "hold"
    assert result.scheduled_irrigation_mm == 0


def test_digest_changes_when_energy_cost_changes():
    first = solve(hourly_forecast=forecast(cost=0.1))
    second = solve(hourly_forecast=forecast(cost=0.4))
    assert first.schedule_digest != second.schedule_digest


def test_missing_source_digest_blocks():
    bad = water()
    bad["soil_profile_digest"] = ""
    result = solve(canonical_water_state=bad)
    assert "COMPLETE_CANONICAL_SOURCE_DIGESTS_REQUIRED" in result.blocking_reasons


def test_required_load_not_permitted_blocks_windows():
    rows = forecast()
    for row in rows:
        row["permitted_load_ids"] = ["pivot-1"]
    result = solve(hourly_forecast=rows)
    assert "NO_FEASIBLE_HOURLY_ENERGY_WINDOW" in result.blocking_reasons


def test_daily_depth_accumulates_across_actions_and_renews_at_utc_midnight():
    rows = forecast(hours=8)
    # All eight rows have the same local date, but UTC midnight falls between them.
    local_midnight = datetime(2026, 7, 14, tzinfo=timezone(timedelta(hours=4)))
    for index, row in enumerate(rows):
        row["hour"] = (local_midnight + timedelta(hours=index)).isoformat()
    cap = {**capability(), "maximum_daily_depth_mm": 6.0, "maximum_safe_depth_mm_event": 4.0}
    result = solve(irrigation_capability=cap, area_ha=4.5, hourly_forecast=rows)

    assert [(a["hour"], a["irrigation_depth_mm"]) for a in result.actions] == [
        ("2026-07-13T20:00:00Z", 4.0),
        ("2026-07-13T21:00:00Z", 2.0),
        ("2026-07-14T00:00:00Z", 4.0),
        ("2026-07-14T01:00:00Z", 2.0),
    ]
    assert result.scheduled_irrigation_mm == 12.0
    assert result.status == "degraded"
    assert result.execution_allowed is False


def test_seasonal_volume_is_shared_across_all_days_in_one_schedule():
    cap = {**capability(), "remaining_seasonal_volume_m3": 95.0}
    rows = forecast(hours=3)
    for index, row in enumerate(rows):
        row["hour"] = (NOW.replace(hour=23) + timedelta(hours=index)).isoformat()
    result = solve(
        irrigation_capability=cap,
        hourly_forecast=rows,
        area_ha=0.5,
        minimum_runtime_minutes=1,
    )

    assert [a["irrigation_volume_m3"] for a in result.actions] == [50.0, 45.0]
    assert result.scheduled_volume_m3 == 95.0
    assert result.status == "degraded"
    assert result.recommendation_only is True


@pytest.mark.parametrize("invalid", [-1, "missing", True, float("nan"), float("inf")])
def test_malformed_seasonal_balance_blocks(invalid):
    result = solve(irrigation_capability={**capability(), "remaining_seasonal_volume_m3": invalid})
    assert result.status == "blocked"
    assert result.actions == []
    assert "INVALID_REMAINING_SEASONAL_VOLUME" in result.blocking_reasons


def test_zero_seasonal_balance_blocks_irrigation():
    result = solve(irrigation_capability={**capability(), "remaining_seasonal_volume_m3": 0})
    assert result.status == "blocked"
    assert result.scheduled_volume_m3 == 0
    assert "SEASONAL_WATER_ALLOCATION_EXHAUSTED" in result.blocking_reasons


def test_fractional_published_actions_stay_inside_both_budgets():
    cap = {
        **capability(),
        "remaining_seasonal_volume_m3": 3.000003,
        "maximum_daily_depth_mm": 1.000001,
        "maximum_safe_depth_mm_event": 0.3333338,
    }
    result = solve(
        irrigation_capability=cap,
        hourly_forecast=forecast(hours=8),
        area_ha=0.3,
        minimum_runtime_minutes=0,
    )
    total_depth = sum(Decimal(str(action["irrigation_depth_mm"])) for action in result.actions)
    total_volume = sum(Decimal(str(action["irrigation_volume_m3"])) for action in result.actions)
    assert Decimal("0.99999") <= total_depth <= Decimal("1.000001")
    assert Decimal("2.99999") <= total_volume <= Decimal("3.000003")


pytestmark = pytest.mark.unit
