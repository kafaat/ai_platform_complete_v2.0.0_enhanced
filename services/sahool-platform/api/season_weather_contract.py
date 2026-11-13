"""Strict season-simulation adapter for owner-produced historical weather products.

The weather-service owns archive provider I/O and canonical observations. This
module verifies dates/provenance before mapping *unchanged* owner values to the
existing RUE/FAO-56 screening engine; it never calculates ET0 or GDD itself.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from api.season_simulation import DayWeather


def _nonnegative(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite numeric measurement or null")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return number


def _temperature(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite numeric measurement or null")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def canonical_historical_days(
    product: dict[str, Any], *, start: date, end: date
) -> list[DayWeather]:
    """Require an exact, provenance-bound daily series for an inclusive season window.

    A truncated or shifted archive is an unavailable dependency, not a shorter
    simulated season. Missing measurements within an existing dated row remain
    null; the engine must not interpret them as observed zeros.
    """
    if end < start:
        raise ValueError("historical weather window ends before it begins")
    if not isinstance(product, dict) or product.get("derived_from") != "canonical_weather_state":
        raise ValueError("historical weather is not a canonical weather-service view")
    if not product.get("canonical_state_id") or not product.get("source_snapshot_id"):
        raise ValueError("historical weather has no canonical state/snapshot identity")
    coverage = product.get("coverage")
    count = (end - start).days + 1
    if not isinstance(coverage, dict):
        raise ValueError("historical weather lacks requested-window coverage proof")
    if (
        coverage.get("period_start") != start.isoformat()
        or coverage.get("period_end") != end.isoformat()
        or coverage.get("expected_days") != count
        or coverage.get("observed_days") != count
        or coverage.get("missing_days") != 0
        or coverage.get("coverage_ratio") != 1.0
    ):
        raise ValueError("historical weather coverage does not match the requested window")
    if product.get("quality_status") in {"invalid", "insufficient", "degraded_incomplete_coverage"}:
        raise ValueError("historical weather owner reports unavailable or incomplete data")
    rows = product.get("days")
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError("historical weather series length mismatch")

    days: list[DayWeather] = []
    for i, row in enumerate(rows):
        expected_date = (start + timedelta(days=i)).isoformat()
        if not isinstance(row, dict) or row.get("date") != expected_date:
            raise ValueError(f"historical weather day {i} is missing, shifted or duplicated")
        tmin = _temperature(row.get("temp_min_c"), f"{expected_date}.temp_min_c")
        tmax = _temperature(row.get("temp_max_c"), f"{expected_date}.temp_max_c")
        if tmin is not None and tmax is not None and tmin > tmax:
            raise ValueError(f"{expected_date}: minimum temperature exceeds maximum")
        days.append(
            DayWeather(
                t_min_c=tmin,
                t_max_c=tmax,
                solar_mj_m2=_nonnegative(
                    row.get("solar_radiation_mj_m2"), f"{expected_date}.solar_radiation_mj_m2"
                ),
                et0_mm=_nonnegative(row.get("et0_mm"), f"{expected_date}.et0_mm"),
                rain_mm=_nonnegative(
                    row.get("precipitation_mm"), f"{expected_date}.precipitation_mm"
                ),
            )
        )
    return days


def validated_engine_daily_series(
    product: dict[str, Any], key: str, expected_days: int
) -> list[float | None]:
    """Reject malformed engine products without reimplementing weather physics."""
    if not isinstance(product, dict):
        raise ValueError(f"weather engine {key} product is not an object")
    series = product.get(key)
    if not isinstance(series, list) or len(series) != expected_days:
        raise ValueError(f"weather engine {key} series length mismatch")
    return [_nonnegative(value, f"{key}[{i}]") for i, value in enumerate(series)]
