"""W1-22 — the ``time='now'`` point/tile sample keeps the hourly-only readings.

sahool-platform now reads its point sample (map tiles, field weather summary, probe,
weather alerts) from ``/v1/weather/tile-data`` instead of its own Open-Meteo connector.
For ``now`` the service built the sample from ``current`` and then blanked ET0, VPD and
soil readings to ``None``, although the hour row holding them was in the same provider
payload. The platform connector filled them from the current hour's row, so moving to the
service lost VPD (spray suitability, heat-stress alerts) and modelled soil moisture.

These tests lock the restored parity: the hourly-only fields come from the row of
``current.time``'s hour (resolved by timestamp, not by position), that row is named in
``time_resolution.hourly_row_time`` with a limitation when it differs from the current
timestamp, a null in that row stays ``None``, and the provider request asks for the
current variables ``normalize_current`` reads (``weather_code``, ``is_day``).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

om = importlib.import_module("open_meteo")

_DAY = "2026-09-05"


def _hourly(hours: int = 48) -> dict:
    """An Open-Meteo hourly block starting at 00:00; each value encodes its own hour."""
    times = [f"2026-09-{5 + h // 24:02d}T{h % 24:02d}:00" for h in range(hours)]
    return {
        "time": times,
        "temperature_2m": [float(h) for h in range(hours)],
        "relative_humidity_2m": [50.0] * hours,
        "precipitation": [0.0] * hours,
        "cloud_cover": [0.0] * hours,
        "wind_speed_10m": [10.0] * hours,
        "wind_direction_10m": [90.0] * hours,
        "wind_gusts_10m": [12.0] * hours,
        "surface_pressure": [1000.0] * hours,
        "et0_fao_evapotranspiration": [h / 100.0 for h in range(hours)],
        "vapour_pressure_deficit": [h / 10.0 for h in range(hours)],
        "soil_temperature_6cm": [20.0 + h for h in range(hours)],
        "soil_moisture_1_to_3cm": [0.1 + h / 1000.0 for h in range(hours)],
        "precipitation_probability": [float(h) for h in range(hours)],
    }


def test_now_sample_reads_hourly_only_fields_from_the_current_hour_row():
    payload = {
        "current": {
            "time": f"{_DAY}T15:10",
            "temperature_2m": 33.3,
            "relative_humidity_2m": 20.0,
            "wind_speed_10m": 7.2,
            "weather_code": 0,
            "is_day": 1,
        },
        "hourly": _hourly(),
    }
    sample = om.normalize_tile_sample(payload, lat=15.0, lon=44.0, time_key="now", model="m")

    # Before the fix these were all None for "now".
    assert sample["vpd_kpa"] == 1.5, f"VPD must come from the 15:00 row, got {sample['vpd_kpa']}"
    assert sample["et0_mm"] == 0.15, f"ET0 must come from the 15:00 row, got {sample['et0_mm']}"
    assert sample["soil_temperature_6cm_c"] == 35.0, "soil temperature from the 15:00 row"
    assert sample["soil_moisture_1_to_3cm_m3m3"] == pytest.approx(0.115), (
        "modelled soil moisture from the 15:00 row"
    )
    assert sample["precipitation_probability_pct"] == 15.0, "rain probability from the 15:00 row"
    assert sample["temperature_c"] == 33.3, "current fields stay from `current`, not the hour row"
    assert sample["weather_code"] == 0, "an observed WMO 0 (clear) is a reading, not absence"
    assert sample["is_day"] is True, "is_day from current"

    resolution = sample["time_resolution"]
    assert resolution["policy"] == "current", "the sample is still the current sample"
    assert resolution["resolved"] == sample["time"] == f"{_DAY}T15:10", "one time for the sample"
    assert resolution["hourly_row_time"] == f"{_DAY}T15:00", "the hour row must be named"
    assert f"hourly_only_fields_from:{_DAY}T15:00" in resolution["limitations"], (
        f"the split must be declared, got {resolution['limitations']}"
    )


def test_now_sample_on_the_hour_declares_no_split():
    payload = {"current": {"time": f"{_DAY}T15:00", "temperature_2m": 1.0}, "hourly": _hourly()}
    sample = om.normalize_tile_sample(payload, lat=15.0, lon=44.0, time_key="now", model="m")
    resolution = sample["time_resolution"]
    assert resolution["hourly_row_time"] == f"{_DAY}T15:00", "the row is the current hour"
    assert not any(x.startswith("hourly_only_fields_from") for x in resolution["limitations"]), (
        f"no split to declare on the hour, got {resolution['limitations']}"
    )


def test_now_sample_keeps_a_null_in_the_hour_row_as_none():
    hourly = _hourly()
    hourly["vapour_pressure_deficit"][15] = None
    payload = {"current": {"time": f"{_DAY}T15:10", "temperature_2m": 30.0}, "hourly": hourly}
    sample = om.normalize_tile_sample(payload, lat=15.0, lon=44.0, time_key="now", model="m")
    assert sample["vpd_kpa"] is None, (
        f"a null VPD at the hour must stay None, not borrow a neighbour: {sample['vpd_kpa']}"
    )
    assert sample["et0_mm"] == 0.15, "the other hourly fields of the row still come through"


def test_now_sample_without_an_hourly_series_stays_none():
    payload = {"current": {"time": f"{_DAY}T15:10", "temperature_2m": 30.0}}
    sample = om.normalize_tile_sample(payload, lat=15.0, lon=44.0, time_key="now", model="m")
    assert sample["vpd_kpa"] is None and sample["et0_mm"] is None, (
        "without an hour row the hourly-only fields are absent, never invented"
    )
    assert sample["time_resolution"]["hourly_row_time"] is None, "no row to name"


async def test_tile_request_asks_for_the_current_and_hourly_variables_it_normalizes(monkeypatch):
    seen: list[dict] = []

    async def fake_fetch_json(url, params):
        seen.append(params)
        return {"current": {"time": f"{_DAY}T15:00"}, "hourly": _hourly()}

    monkeypatch.setattr(om, "_fetch_json", fake_fetch_json)
    await om.fetch_tile_sample(15.0, 44.0, time_key="now")

    current = set(seen[0]["current"].split(","))
    hourly = set(seen[0]["hourly"].split(","))
    assert {"weather_code", "is_day", "pressure_msl"} <= current, (
        f"normalize_current reads weather_code/is_day, the request must ask for them: {current}"
    )
    assert {"vapour_pressure_deficit", "et0_fao_evapotranspiration", "soil_moisture_1_to_3cm"} <= (
        hourly
    ), f"the hourly-only fields must be requested: {hourly}"
