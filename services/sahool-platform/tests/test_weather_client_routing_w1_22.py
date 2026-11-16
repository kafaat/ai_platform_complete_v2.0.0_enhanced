"""W1-22 — platform weather goes through weather_service_client; absence never becomes 0.

Covers the fields-12 / weather-4 / weather-6 / routes-8 findings:

* the AI context pack (``field_ai_context``) summed ``float(x or 0)`` over the historical
  series, so a day without a rain or ET0 reading counted as a dry day and the advisor
  received a smaller total labelled complete (weather-4);
* the typed readings that replace the Open-Meteo connector keep ``None`` for an absent,
  null, non-numeric, boolean or non-finite value, and refuse a view without ``days``;
* the point sample used by tiles / alerts / probe comes from weather-service and raises on
  a neutral tile instead of returning an empty sample.

Only the HTTP transport (``weather_get_json``) is replaced; the real adapters run.
"""

from __future__ import annotations

import math

import pytest

pytestmark = pytest.mark.unit


def _historical_view(days: list[dict]) -> dict:
    return {
        "derived_from": "canonical_weather_state",
        "canonical_state_id": "st-1",
        "source_snapshot_id": "snap-1",
        "quality_status": "degraded",
        "coverage": {"expected_days": len(days), "observed_days": len(days)},
        "limitations": ["historical: one day has no precipitation reading"],
        "days": days,
    }


_DAYS_WITH_A_GAP = [
    {
        "date": "2026-01-30",
        "temp_max_c": 20.0,
        "temp_min_c": 10.0,
        "precipitation_mm": 4.0,
        "et0_mm": 3.0,
    },
    {
        "date": "2026-01-31",
        "temp_max_c": 22.0,
        "temp_min_c": 12.0,
        "precipitation_mm": None,
        "et0_mm": 3.5,
    },
    {
        "date": "2026-02-01",
        "temp_max_c": 24.0,
        "temp_min_c": 14.0,
        "precipitation_mm": 0.0,
        "et0_mm": 4.0,
    },
]


# ── the AI pack: an incomplete total is None, not a smaller sum ─────────────────────
def test_pack_summary_never_turns_a_missing_reading_into_zero():
    from api.routers.field_ai_context import summarize_weather_history
    from api.weather_service_client import daily_from_view

    records = daily_from_view(_historical_view(_DAYS_WITH_A_GAP))
    summary, monthly = summarize_weather_history(records)

    # Before W1-22 this was 4.0: the missing day was added as 0.0 mm.
    assert summary["total_precipitation_mm"] is None, (
        f"a missing rain day was summed as zero: {summary['total_precipitation_mm']}"
    )
    assert summary["precipitation_days_missing"] == 1, "the missing day must be counted"
    assert summary["total_et0_mm"] == 10.5, "a complete ET0 series must still total"
    assert summary["et0_days_missing"] == 0, "no ET0 day is missing"
    # The observed-only total keeps the rain signal, labelled with its observed-day count.
    assert summary["observed_precipitation_mm"] == 4.0, "observed days sum only what was observed"
    assert summary["precipitation_days_observed"] == 2, "two of three days have a rain reading"
    assert summary["observed_et0_mm"] == 10.5, "ET0 observed on every day"
    assert summary["et0_days_observed"] == 3, "all three days have ET0"

    by_month = {m["month"]: m for m in monthly}
    assert by_month["2026-01"]["precipitation_mm"] is None, (
        "a month with a missing rain day must not report a partial total"
    )
    assert by_month["2026-01"]["precipitation_days_missing"] == 1, "January misses one day"
    # An observed 0.0 mm is a reading, not an absence: February totals to 0.0.
    assert by_month["2026-02"]["precipitation_mm"] == 0.0, "observed zero rain must stay 0.0"
    assert by_month["2026-02"]["precipitation_days_missing"] == 0, "February is complete"


def test_pack_summary_of_a_complete_series_still_totals():
    from api.routers.field_ai_context import summarize_weather_history
    from api.weather_service_client import daily_from_view

    days = [dict(d, precipitation_mm=1.5) for d in _DAYS_WITH_A_GAP]
    summary, _monthly = summarize_weather_history(daily_from_view(_historical_view(days)))
    assert summary["total_precipitation_mm"] == 4.5, "a complete rain series must total"
    assert summary["avg_temp_c"] == 17.0, "mean temperature over the complete days"


async def test_pack_reads_weather_service_with_the_tenant_and_reports_incomplete(monkeypatch):
    from api import weather_service_client
    from api.routers import field_ai_context

    calls: list[tuple[str, dict]] = []

    async def fake_weather_get_json(path, **kwargs):
        calls.append((path, kwargs))
        return _historical_view(_DAYS_WITH_A_GAP)

    monkeypatch.setattr(weather_service_client, "weather_get_json", fake_weather_get_json)

    pack, warning = await field_ai_context._optional_weather_history(
        {"lat": 15.0, "lon": 44.0}, 30, "tenant-a"
    )

    assert warning is None, f"unexpected warning: {warning}"
    assert calls and calls[0][0] == "/v1/weather/historical", (
        f"the pack must read the weather-service historical view, called {calls}"
    )
    assert calls[0][1].get("tenant_id") == "tenant-a", "the tenant identity must be forwarded"
    assert pack["source"] == "weather-service", "the pack must name weather-service as source"
    assert pack["summary"]["total_precipitation_mm"] is None, (
        "the pack turned a missing rain reading into a number"
    )
    assert pack["quality_status"] == "degraded", "the owner's quality must reach the pack"
    assert pack["limitations"], "the owner's limitations must reach the pack"

    text = field_ai_context._summary_ar({"weather_history": pack, "days": 30, "field_id": "f1"})
    assert "مطر تراكمي غير مكتمل" in text, f"the Arabic summary hides the gap: {text}"
    assert "None" not in text, f"the Arabic summary leaks a raw None: {text}"


async def test_pack_weather_service_failure_is_unavailable_not_zero(monkeypatch):
    from api import weather_service_client
    from api.routers import field_ai_context

    async def unavailable(path, **kwargs):
        raise RuntimeError("weather-service down")

    monkeypatch.setattr(weather_service_client, "weather_get_json", unavailable)
    pack, warning = await field_ai_context._optional_weather_history(
        {"lat": 15.0, "lon": 44.0}, 30, "tenant-a"
    )
    assert pack["available"] is False, "a failed read must mark the history unavailable"
    assert pack["summary"] == {}, "a failed read must not carry any total"
    assert warning, "a failed read must surface a warning"


# ── the typed readings: absence stays None ─────────────────────────────────────────
@pytest.mark.parametrize("value", [None, "n/a", True, float("nan"), float("inf")])
def test_reading_keeps_absence_as_none(value):
    from api.weather_service_client import reading

    assert reading({"k": value}, "k") is None, f"{value!r} must read as absent, not a number"
    assert reading({}, "k") is None, "a missing key must read as absent"


def test_reading_keeps_an_observed_zero():
    from api.weather_service_client import reading

    assert reading({"k": 0}, "k") == 0.0, "an observed zero is a reading"


def test_current_view_absence_reaches_the_caller_as_none():
    from api.weather_service_client import current_from_view

    current = current_from_view(
        {
            "temperature_c": None,
            "humidity_pct": 41.0,
            "precipitation_mm": 0.0,
            "weather_code": None,
            "is_day": 1,
            "missing_fields": ["temperature_c", "weather_code"],
            "quality_status": "degraded",
        }
    )
    assert current.temperature_c is None, "absent temperature must stay None"
    assert current.weather_code is None, "absent WMO code must stay None (not 0 = clear sky)"
    assert current.precipitation_mm == 0.0, "observed zero rain must stay 0.0"
    assert current.is_day is None, "a non-boolean is_day is not a reading"
    assert current.missing_fields == ("temperature_c", "weather_code"), "missing names kept"
    assert current.source == "weather-service", "readings name their source"


def test_daily_view_without_days_is_an_error_not_an_empty_forecast():
    from api.weather_service_client import daily_from_view

    with pytest.raises(ValueError, match="days"):
        daily_from_view({"time": ["2026-03-01"], "precipitation_mm": [1.0]})


# ── tiles / alerts / probe: the point sample comes from weather-service ────────────
def test_point_sample_tile_contains_the_point():
    from api.weather_service_client import point_sample_tile

    z, x, y = point_sample_tile(15.35, 44.21)
    n = 2**z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    assert z == 18, "the point sample uses the highest tile zoom weather-service accepts"
    assert west <= 44.21 < east, f"tile x={x} does not contain the longitude"
    assert south < 15.35 <= north, f"tile y={y} does not contain the latitude"


def _load_weather_service_open_meteo():
    """The real weather-service sample producer, loaded by path under a private name.

    The platform consumes what weather-service produces; faking the producer with a
    platform-shaped sample is how the schema mismatch went unnoticed (W1-22 review).
    """
    import importlib.util
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    path = repo / "services" / "weather-service" / "open_meteo.py"
    spec = importlib.util.spec_from_file_location("_w1_22_weather_service_open_meteo", path)
    assert spec and spec.loader, f"cannot load the weather-service producer at {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _open_meteo_payload(temp_c: float | None, rh_pct: float | None) -> dict:
    hours = ["2026-07-01T12:00", "2026-07-01T13:00", "2026-07-01T14:00", "2026-07-01T15:00"]
    n = len(hours)
    return {
        "timezone": "Asia/Aden",
        "current": {
            "time": hours[0],
            "temperature_2m": temp_c,
            "relative_humidity_2m": rh_pct,
            "wind_speed_10m": 6.0,
            "wind_direction_10m": 0.0,
            "wind_gusts_10m": 9.0,
            "precipitation": 0.0,
            "cloud_cover": 10.0,
            "surface_pressure": 950.0,
            "weather_code": 0,
            "is_day": 1,
        },
        "hourly": {
            "time": hours,
            "temperature_2m": [temp_c] * n,
            "relative_humidity_2m": [rh_pct] * n,
            "precipitation": [0.0] * n,
            "cloud_cover": [10.0] * n,
            "wind_speed_10m": [6.0] * n,
            "wind_gusts_10m": [9.0] * n,
            "wind_direction_10m": [0.0] * n,
            "et0_fao_evapotranspiration": [0.6] * n,
            "vapour_pressure_deficit": [0.6] * n,
            "soil_temperature_6cm": [35.0] * n,
            "soil_moisture_1_to_3cm": [0.2] * n,
            "surface_pressure": [950.0] * n,
        },
    }


def _service_tile(sample: dict, **extra) -> dict:
    return {"sample": sample, "cache_state": "refreshed", "cache_age_s": 0, **extra}


@pytest.mark.parametrize("time_key", ["now", "+2h"])
async def test_heat_wave_from_the_real_service_sample_still_blocks_spraying(monkeypatch, time_key):
    """41 °C / 92 % RH from weather-service must raise heat_wave and make spraying poor.

    Before the review fix the platform read ``temperature_2m_c`` from a sample keyed
    ``temperature_c``: every reading was None, spraying scored 1.0 (optimal) and the alerts
    recommended an "excellent spray window" in a heat wave.
    """
    from api import weather_service_client
    from api.routers import weather
    from api.weather_alerts import derive_weather_alerts

    om = _load_weather_service_open_meteo()
    service_sample = om.normalize_tile_sample(
        _open_meteo_payload(41.0, 92.0), lat=15.35, lon=44.21, time_key=time_key, model="best_match"
    )
    assert service_sample.get("temperature_c") == 41.0, (
        f"producer contract changed; the fixture no longer reflects it: {service_sample}"
    )

    async def fake_weather_get_json(path, **kwargs):
        assert path.startswith("/v1/weather/tile-data/18/"), f"unexpected path {path}"
        return _service_tile(service_sample)

    monkeypatch.setattr(weather_service_client, "weather_get_json", fake_weather_get_json)
    sample = await weather_service_client.get_point_weather_sample(15.35, 44.21, time=time_key)

    assert sample["temperature_2m_c"] == 41.0, f"temperature lost in translation: {sample}"
    assert sample["relative_humidity_2m_pct"] == 92.0, f"humidity lost in translation: {sample}"
    assert weather._safe_layer_value("temperature", sample) == 41.0, (
        "the temperature map layer must show the service reading, not null"
    )

    spraying = weather._operation_suitability(sample, "spraying")
    assert spraying["suitability"] in {"poor", "unsafe"}, f"spraying in a heat wave: {spraying}"
    assert "temperature_outside_spray_window" in spraying["limiting_factors"], (
        f"temperature not considered: {spraying}"
    )
    assert "humidity_high" in spraying["limiting_factors"], f"humidity not considered: {spraying}"

    alerts = derive_weather_alerts(sample)
    types = {a["type"]: a["severity"] for a in alerts}
    assert types.get("heat_wave") == "critical", f"no critical heat_wave alert: {alerts}"
    assert "excellent_spray_window" not in types, f"spray window offered in a heat wave: {alerts}"
    assert weather._sample_alerts_ar(sample), "the Arabic field alerts must flag the heat"


async def test_platform_sample_keeps_zero_and_absence_apart():
    from api.weather_service_client import platform_sample_from_service

    zero = platform_sample_from_service(
        {"temperature_c": 0.0, "humidity_pct": 100.0, "precipitation_mm": 0.0, "vpd_kpa": None}
    )
    assert zero["temperature_2m_c"] == 0.0, f"0 °C is a reading (frost), not absence: {zero}"
    assert zero["precipitation_mm"] == 0.0, "observed zero rain must stay 0.0"
    assert zero["vapour_pressure_deficit_kpa"] is None, (
        "VPD is not derived in the platform (the formula belongs to the weather engine)"
    )

    absent = platform_sample_from_service({"temperature_c": 30.0, "humidity_pct": None})
    for key in (
        "relative_humidity_2m_pct",
        "vapour_pressure_deficit_kpa",
        "pressure_msl_hpa",
        "precipitation_mm",
        "et0_fao_evapotranspiration_mm",
        "soil_temperature_0cm_c",
    ):
        assert absent[key] is None, f"{key} must stay None when the service has no reading"


def test_frost_reading_is_not_replaced_by_the_mild_default():
    from api.routers import weather

    frost = {"temperature_2m_c": 0.0, "relative_humidity_2m_pct": 60.0}
    spraying = weather._operation_suitability(frost, "spraying")
    assert "temperature_outside_spray_window" in spraying["limiting_factors"], (
        f"0 °C was read as the 25 °C default: {spraying}"
    )


async def test_stale_service_sample_is_reported_stale_and_not_cached_fresh(monkeypatch):
    from api import weather_service_client
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def stale_tile(path, **kwargs):
        return _service_tile(
            {"temperature_c": 31.0, "humidity_pct": 40.0},
            cache_state="stale_fallback",
            cache_age_s=3000,
            upstream_error="open-meteo timeout",
        )

    monkeypatch.setattr(weather_service_client, "weather_get_json", stale_tile)

    sample, state, age, err = await weather._get_weather_sample_cached(
        15.35, 44.21, "now", "best_match", "w1-22-stale"
    )
    assert sample["temperature_2m_c"] == 31.0, "the stale sample is still served"
    assert state == "stale_fallback", f"a stale service sample was reported as {state}"
    assert age == 3000, f"the service's cache age must reach the caller, got {age}"
    assert err == "open-meteo timeout", f"the upstream error was dropped: {err}"
    assert not any("w1-22-stale" in str(k) for k in weather._WEATHER_TILE_CACHE), (
        "a stale service sample must not be cached as fresh by the platform"
    )

    probe = await weather.weather_probe(15.35, 44.21, time="now", model="best_match")
    assert probe["cache_state"] == "stale_fallback", f"probe hid staleness: {probe['cache_state']}"
    assert probe["cache_age_s"] == 3000, "probe must report the service's cache age"
    assert probe["upstream_error"] == "open-meteo timeout", "probe must report the upstream error"


async def test_point_sample_raises_on_a_neutral_tile(monkeypatch):
    from api import weather_service_client

    async def neutral(path, **kwargs):
        return {"value": None, "sample": None, "cache_state": "unavailable"}

    monkeypatch.setattr(weather_service_client, "weather_get_json", neutral)
    with pytest.raises(RuntimeError, match="unavailable"):
        await weather_service_client.get_point_weather_sample(15.35, 44.21)


async def test_weather_automation_reads_weather_service_and_keeps_absence(monkeypatch):
    from api import weather_service_client
    from api.weather_automation import WeatherAutomation

    async def fake_weather_get_json(path, **kwargs):
        assert path == "/v1/weather/current", f"automation must read current weather, got {path}"
        return {"temperature_c": None, "weather_code": None, "precipitation_mm": 0.0}

    monkeypatch.setattr(weather_service_client, "weather_get_json", fake_weather_get_json)
    wa = WeatherAutomation()

    async def no_db():
        return None

    async def no_persist(*_a, **_kw):
        return None

    monkeypatch.setattr(wa, "sync_from_db", no_db)
    monkeypatch.setattr(wa, "_persist_cache", no_persist)
    wa.register_location(15.0, 44.0, field_id="f1")
    result = await wa.refresh_all()

    assert result["refreshed"] == 1, f"the reading must be cached: {result}"
    payload = wa.get_cached(15.0, 44.0).data
    assert payload["source"] == "weather-service", "the cached payload must name its source"
    assert payload["temperature_c"] is None, "absent temperature must stay None"
    assert payload["weather_ar"] == "غير معروف", "an absent WMO code is unknown, not clear"
