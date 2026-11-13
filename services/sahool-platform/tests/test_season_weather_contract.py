"""Canonical historical weather and daily-engine alignment guards for season simulation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from api.season_weather_contract import (
    canonical_historical_days,
    validated_engine_daily_series,
)

pytestmark = pytest.mark.unit


def _product(*, start=date(2026, 1, 1), count=3):
    end = start + timedelta(days=count - 1)
    return {
        "derived_from": "canonical_weather_state",
        "canonical_state_id": "wx-state-123",
        "source_snapshot_id": "wx-snapshot-123",
        "quality_status": "validated",
        "coverage": {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "expected_days": count,
            "observed_days": count,
            "missing_days": 0,
            "coverage_ratio": 1.0,
        },
        "days": [
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "temp_min_c": 12.0,
                "temp_max_c": 29.0,
                "solar_radiation_mj_m2": 20.0,
                "et0_mm": 5.0,
                "precipitation_mm": 0.0,
            }
            for i in range(count)
        ],
    }


def test_canonical_archive_preserves_observations_without_weather_recalculation():
    product = _product()
    product["days"][1]["precipitation_mm"] = None
    product["days"][1]["temp_min_c"] = None
    out = canonical_historical_days(product, start=date(2026, 1, 1), end=date(2026, 1, 3))
    assert len(out) == 3
    assert out[1].rain_mm is None
    assert out[1].t_min_c is None
    assert out[1].solar_mj_m2 == 20.0
    assert out[2].et0_mm == 5.0


@pytest.mark.parametrize(
    "reason", ["missing_day", "duplicate_date", "wrong_coverage", "no_provenance"]
)
def test_archive_with_missing_or_untraceable_days_is_rejected(reason):
    product = _product()
    if reason == "missing_day":
        product["days"].pop()
    elif reason == "duplicate_date":
        product["days"][1]["date"] = product["days"][0]["date"]
    elif reason == "wrong_coverage":
        product["coverage"]["expected_days"] = 4
    else:
        product["canonical_state_id"] = None
    with pytest.raises(ValueError):
        canonical_historical_days(product, start=date(2026, 1, 1), end=date(2026, 1, 3))


def test_silent_day_shift_is_refused_even_when_length_matches():
    product = _product()
    product["days"][0]["date"] = "2025-12-31"
    with pytest.raises(ValueError, match="shifted"):
        canonical_historical_days(product, start=date(2026, 1, 1), end=date(2026, 1, 3))


@pytest.mark.parametrize(
    "field,value",
    [
        ("temp_min_c", float("nan")),
        ("temp_max_c", float("inf")),
        ("et0_mm", -1.0),
        ("precipitation_mm", -0.1),
        ("solar_radiation_mj_m2", float("inf")),
    ],
)
def test_archive_rejects_invalid_measurements(field, value):
    product = _product()
    product["days"][1][field] = value
    with pytest.raises(ValueError):
        canonical_historical_days(product, start=date(2026, 1, 1), end=date(2026, 1, 3))


def test_missing_daily_et0_and_gdd_are_null_not_zero():
    series = validated_engine_daily_series({"daily_gdd": [0.0, None, 12.0]}, "daily_gdd", 3)
    assert series == [0.0, None, 12.0]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0, True, "3"])
def test_invalid_engine_daily_values_are_rejected(value):
    with pytest.raises(ValueError):
        validated_engine_daily_series({"daily_gdd": [12.0, value]}, "daily_gdd", 2)


def test_partial_engine_series_cannot_be_shifted_onto_other_days():
    with pytest.raises(ValueError, match="length mismatch"):
        validated_engine_daily_series({"daily_et0_mm": [5.0, 4.0]}, "daily_et0_mm", 3)
