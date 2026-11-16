"""Regression: weather archive aggregates must not present missing ET0/rain as zero."""
from types import SimpleNamespace

import pytest

from api.field_context import summarize_ai_weather_archive

pytestmark = pytest.mark.unit


def _day(date, rain, et0):
    return SimpleNamespace(
        date=date,
        temp_max_c=32.0,
        temp_min_c=20.0,
        precipitation_mm=rain,
        et0_mm=et0,
    )


def test_incomplete_weather_totals_are_unknown_not_zero():
    summary, monthly, rain_complete, et0_complete = summarize_ai_weather_archive(
        [
            _day("2026-11-14", 0.0, 4.0),
            _day("2026-11-15", None, None),
        ]
    )
    assert not rain_complete and not et0_complete
    assert summary["total_precipitation_mm"] is None
    assert summary["total_et0_mm"] is None
    assert summary["precipitation_covered_days"] == 1
    assert monthly[0]["precipitation_mm"] is None
    assert monthly[0]["et0_mm"] is None


def test_real_observed_zero_remains_zero():
    summary, monthly, rain_complete, et0_complete = summarize_ai_weather_archive(
        [_day("2026-11-14", 0.0, 0.0)]
    )
    assert rain_complete and et0_complete
    assert summary["total_precipitation_mm"] == 0.0
    assert summary["total_et0_mm"] == 0.0
    assert monthly[0]["precipitation_mm"] == 0.0
