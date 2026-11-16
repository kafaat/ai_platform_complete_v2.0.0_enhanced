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


async def test_point_sample_reads_weather_service_tile_data(monkeypatch):
    from api import weather_service_client

    seen: list[str] = []

    async def fake_weather_get_json(path, **kwargs):
        seen.append(path)
        return {"sample": {"temperature_2m_c": 30.0}, "cache_state": "fresh"}

    monkeypatch.setattr(weather_service_client, "weather_get_json", fake_weather_get_json)
    sample = await weather_service_client.get_point_weather_sample(15.35, 44.21)
    assert sample == {"temperature_2m_c": 30.0}, "the tile's sample must be returned as is"
    assert seen and seen[0].startswith("/v1/weather/tile-data/18/"), (
        f"the point sample must come from weather-service tile-data, got {seen}"
    )


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
