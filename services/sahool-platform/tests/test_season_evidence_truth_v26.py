"""Season RUE/FAO-56 evidence guards: missing data must never become observed zero."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from api.season_simulation import (
    DayWeather,
    SimContext,
    SimWindowError,
    plan_simulation_window,
    simulate_season,
    validate_historical_weather_window,
)

pytestmark = pytest.mark.unit


def _context(
    *,
    gdd: list[float | None] | None = None,
    et0: list[float | None] | None = None,
    rain: float | None = 0.0,
) -> SimContext:
    n = 10
    return SimContext(
        crop="wheat",
        weather=[
            DayWeather(
                t_min_c=12.0,
                t_max_c=24.0,
                solar_mj_m2=19.0,
                et0_mm=4.0,
                rain_mm=rain,
            )
            for _ in range(n)
        ],
        gdd_daily_override=gdd,
        et0_daily_override=et0,
    )


def test_observed_zero_gdd_is_not_missing():
    out = simulate_season(_context(gdd=[0.0] * 10))
    assert out.gdd_total == 0.0
    assert out.yield_kg_ha == 0.0
    assert out.yield_status == "estimated"


def test_no_gdd_is_not_observed_zero_yield():
    out = simulate_season(_context(gdd=None))
    assert out.gdd_total is None
    assert out.maturity_reached is None
    assert out.lai_max is None
    assert out.biomass_kg_ha is None
    assert out.yield_kg_ha is None
    assert out.yield_low_kg_ha is None
    assert out.yield_status == "unavailable_missing_gdd"
    assert out.confidence == 0.0
    assert "GDD_SERIES_INCOMPLETE" in out.limitations


def test_one_missing_gdd_day_rejects_season_wide_yield():
    out = simulate_season(_context(gdd=[12.0] * 9 + [None]))
    assert out.gdd_total is None
    assert out.yield_kg_ha is None
    assert out.yield_status == "unavailable_missing_gdd"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, True])
def test_invalid_gdd_is_absence_not_zero(bad):
    out = simulate_season(_context(gdd=[12.0] * 9 + [bad]))
    assert out.gdd_total is None
    assert out.yield_status == "unavailable_missing_gdd"


def test_canonical_et0_none_cannot_fallback_to_legacy_day_value():
    gdd = [12.0] * 10
    out = simulate_season(_context(gdd=gdd, et0=[5.0] * 9 + [None]))
    assert out.water_need_mm is None
    assert out.water_stress_factor is None
    assert out.yield_kg_ha is None
    assert out.yield_status == "unavailable_missing_et0"


def test_missing_precipitation_is_not_zero_rain():
    out = simulate_season(_context(gdd=[12.0] * 10, rain=None))
    assert out.water_need_mm is not None
    assert out.water_supply_mm is None
    assert out.water_stress_factor is None
    assert out.yield_kg_ha is None
    assert out.yield_status == "unavailable_missing_precipitation"


def test_true_dry_weather_with_complete_inputs_allows_screening():
    out = simulate_season(_context(gdd=[12.0] * 10, rain=0.0))
    assert out.water_need_mm is not None
    assert out.yield_kg_ha is not None
    assert out.yield_status == "estimated"


def test_empty_weather_has_no_fabricated_metrics():
    out = simulate_season(SimContext(crop="wheat", weather=[]))
    assert out.days_simulated == 0
    assert out.gdd_total is None
    assert out.yield_kg_ha is None
    assert out.water_need_mm is None
    assert out.yield_status == "unavailable_no_weather"


def _days(start: date, count: int):
    return [SimpleNamespace(date=(start + timedelta(days=i)).isoformat()) for i in range(count)]


def test_valid_archive_day_sequence_is_accepted():
    start = date(2026, 1, 1)
    validate_historical_weather_window(_days(start, 5), start, start + timedelta(days=4))


def test_archive_missing_or_duplicate_days_is_rejected():
    start = date(2026, 1, 1)
    end = start + timedelta(days=4)
    with pytest.raises(SimWindowError):
        validate_historical_weather_window(_days(start, 4), start, end)
    duplicate = _days(start, 5)
    duplicate[2] = SimpleNamespace(date=duplicate[1].date)
    with pytest.raises(SimWindowError):
        validate_historical_weather_window(duplicate, start, end)


def test_inverted_season_dates_are_refused_instead_of_extended():
    with pytest.raises(SimWindowError, match="يسبق تاريخ البذار"):
        plan_simulation_window(
            "wheat",
            date(2026, 4, 1),
            date(2026, 3, 25),
            date(2026, 11, 13),
            floor_days=160,
        )
