"""W1-09 / W1-10: the season state reads its thermal time from weather-service, one stage resolver.

crop-2 / weather-12: ``GET /fields/{id}/seasons/{sid}/state`` passed ``accumulated_gdd=None``,
no forecast and no weather signals, so the stage was always calendar-only. These tests pin
``gather_season_weather_inputs`` (archive, then engine GDD at the crop-card base, then a
seven-day forecast) and what the state does with it. The weather fetchers are stubbed at the
client-function level; no database is involved (the route itself is covered live in
``tests_v9/test_season_state_sources_live_pg.py``).

crop-3 / W1-10: ``core.gdd_phenology.phenology_progress`` is the single stage resolver for the
season state, ``field_context._season_stage``, ``/phenology`` and the agronomic state engine,
with a declared calendar fallback.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from api.field_season_projection import (
    SEASON_ARCHIVE_LAG_DAYS,
    assemble_field_season_state,
    forecast_stage_signals,
    gather_season_weather_inputs,
)
from core.gdd_phenology import gdd_base_c, phenology_progress
from fastapi import HTTPException

pytestmark = pytest.mark.unit

TODAY = date(2026, 1, 20)
SOWING = date(2025, 11, 1)
DAILY_GDD = 18.0


def _archive(start: date, end: date) -> dict:
    n = (end - start).days + 1
    return {
        "derived_from": "canonical_weather_state",
        "canonical_state_id": "cws-1",
        "source_snapshot_id": "snap-1",
        "quality_status": "validated",
        "coverage": {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "expected_days": n,
            "observed_days": n,
            "missing_days": 0,
            "coverage_ratio": 1.0,
        },
        "days": [
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "temp_min_c": 8.0,
                "temp_max_c": 28.0,
            }
            for i in range(n)
        ],
    }


def _forecast(days: int = 7, **override) -> dict:
    rows = []
    for i in range(days):
        row = {
            "date": (TODAY + timedelta(days=i)).isoformat(),
            "temp_min_c": 10.0,
            "temp_max_c": 26.0 + i,
            "precipitation_mm": 1.0,
            "wind_max_kmh": 20.0,
            "rh_mean_pct": 40.0,
        }
        row.update(override)
        rows.append(row)
    return {"days": rows}


class Recorder:
    """Client-function stubs that record what the gatherer asked weather-service for."""

    def __init__(self, *, historical=None, gdd_quality="validated", forecast=None):
        self.calls: list[tuple[str, dict]] = []
        self._historical = historical
        self._gdd_quality = gdd_quality
        self._forecast = forecast

    async def get_historical(self, lat, lon, *, start_date, end_date, tenant_id=None):
        self.calls.append(("historical", {"start": start_date, "end": end_date, "t": tenant_id}))
        if isinstance(self._historical, Exception):
            raise self._historical
        return self._historical or _archive(
            date.fromisoformat(start_date), date.fromisoformat(end_date)
        )

    async def get_gdd(self, *, daily_t_min, daily_t_max, base_c, upper_cutoff_c, method, **kw):
        self.calls.append(("gdd", {"base_c": base_c, "n": len(daily_t_min), "method": method}))
        n = len(daily_t_min)
        return {
            "daily_gdd": [DAILY_GDD] * n,
            "accumulated_gdd": DAILY_GDD * n,
            "quality_status": self._gdd_quality,
            "thresholds_used": {"base_c": base_c, "upper_cutoff_c": upper_cutoff_c},
            "calculation_version": "gdd/daily/1.0.0",
            "valid_period": {"start_date": kw.get("start_date"), "end_date": kw.get("end_date")},
        }

    async def get_forecast(self, lat, lon, *, days=7):
        self.calls.append(("forecast", {"days": days}))
        if isinstance(self._forecast, Exception):
            raise self._forecast
        return self._forecast or _forecast(days)


async def _gather(rec: Recorder, **kw) -> dict:
    args = {
        "crop": "wheat",
        "sowing_date": SOWING,
        "as_of": TODAY,
        "today": TODAY,
        "lat": 15.3,
        "lon": 44.2,
        "tenant_id": "t-1",
        "get_historical": rec.get_historical,
        "get_gdd": rec.get_gdd,
        "get_forecast": rec.get_forecast,
    }
    args.update(kw)
    return await gather_season_weather_inputs(**args)


async def test_season_state_has_gdd_and_gdd_stage_when_weather_is_available():
    """Acceptance (W1-09): non-null accumulated_gdd and stage_source='gdd'."""
    rec = Recorder()
    weather = await _gather(rec)
    end = TODAY - timedelta(days=SEASON_ARCHIVE_LAG_DAYS)
    expected_days = (end - SOWING).days + 1
    assert weather["accumulated_gdd"] == pytest.approx(DAILY_GDD * expected_days), (
        "the engine's accumulated GDD over sowing..(today - reanalysis lag) must be used"
    )
    assert weather["accumulated_gdd_through"] == end.isoformat(), (
        "the state must declare the last day its thermal sum covers"
    )
    state = assemble_field_season_state(
        crop="wheat",
        sowing_date=SOWING,
        today=TODAY,
        accumulated_gdd=weather["accumulated_gdd"],
        weather_signals=weather["weather_signals"],
        forecast_daily=weather["forecast_daily"],
    )
    assert state["accumulated_gdd"] is not None, "season state must carry the thermal sum"
    assert state["stage_source"] == "gdd", "with weather available the stage must be thermal"
    assert state["stage_fallback"] is None, "no fallback is declared for a thermal stage"
    assert "accumulated_gdd" in state["evidence_used"], "GDD must count as used evidence"
    assert "weather" in state["evidence_used"], "forecast signals must reach stage risks"


async def test_gdd_is_requested_at_the_crop_card_base_for_the_archive_window():
    rec = Recorder()
    await _gather(rec)
    hist = [c for k, c in rec.calls if k == "historical"]
    gdd = [c for k, c in rec.calls if k == "gdd"]
    assert hist == [
        {
            "start": SOWING.isoformat(),
            "end": (TODAY - timedelta(days=SEASON_ARCHIVE_LAG_DAYS)).isoformat(),
            "t": "t-1",
        }
    ], "the archive is read once, from sowing, tenant-scoped, ending before the reanalysis lag"
    assert gdd and gdd[0]["base_c"] == gdd_base_c("wheat"), (
        "the GDD base must be the crop card's thermal.gdd_base_c"
    )
    assert all(c["method"] == "modified" for c in gdd), "the engine method is declared"


async def test_forecast_gets_engine_gdd_and_complete_signals():
    rec = Recorder()
    weather = await _gather(rec)
    daily = weather["forecast_daily"]
    assert len(daily) == 7, "a seven-day forecast is requested"
    assert all(d["gdd"] == DAILY_GDD for d in daily), "forecast GDD comes from the engine"
    assert weather["weather_signals"] == {
        "tmax_c": 32.0,
        "tmin_c": 10.0,
        "wind_kmh": 20.0,
        "rain_mm_next_7d": 7.0,
        "rh_pct": 40.0,
    }, "signals aggregate the whole forecast horizon"
    assert weather["unavailable"] == [], "nothing is declared missing when every source answers"


def test_partial_forecast_column_is_absent_not_a_smaller_total():
    rows = _forecast()["days"]
    rows[3]["precipitation_mm"] = None
    signals = forecast_stage_signals(rows)
    assert "rain_mm_next_7d" not in signals, "a missing rain day must not become a lower total"
    assert signals["tmax_c"] == 32.0, "complete columns still produce their signal"


async def test_closed_season_skips_the_forecast():
    rec = Recorder()
    weather = await _gather(rec, as_of=date(2025, 12, 31))
    assert [k for k, _ in rec.calls].count("forecast") == 0, "no forecast for a closed season"
    assert weather["accumulated_gdd_through"] == "2025-12-31", "a closed season sums to its end"
    assert weather["forecast_daily"] is None, "a closed season has no forecast block"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"lat": None}, "field_location_missing"),
        ({"sowing_date": None}, "sowing_date_missing"),
        ({"sowing_date": TODAY - timedelta(days=2)}, "archive_window_inside_reanalysis_lag"),
    ],
)
async def test_missing_inputs_are_declared_not_invented(kwargs, reason):
    weather = await _gather(Recorder(), **kwargs)
    assert weather["accumulated_gdd"] is None, "no thermal sum without its inputs"
    assert reason in weather["unavailable"], f"the reason {reason} must be declared"


async def test_weather_service_down_leaves_gdd_none_and_calendar_stage():
    rec = Recorder(historical=HTTPException(status_code=502, detail="down"))
    weather = await _gather(rec)
    assert weather["accumulated_gdd"] is None, "an unavailable archive yields no GDD"
    assert "weather_historical_unavailable" in weather["unavailable"], "the failure is named"
    state = assemble_field_season_state(
        crop="wheat", sowing_date=SOWING, today=TODAY, accumulated_gdd=weather["accumulated_gdd"]
    )
    assert state["stage_source"] == "days", "the stage falls back to the calendar"
    assert state["stage_fallback"] == "calendar_days", "the fallback is declared"
    assert state["stage_fallback_reason"] == "accumulated_gdd_missing", "with its reason"


async def test_degraded_engine_gdd_is_not_used_as_a_lower_sum():
    weather = await _gather(Recorder(gdd_quality="degraded"))
    assert weather["accumulated_gdd"] is None, "a sum with missing days understates thermal time"
    assert "weather_gdd_incomplete" in weather["unavailable"], "the incompleteness is declared"


async def test_truncated_archive_is_refused():
    short = _archive(SOWING, TODAY - timedelta(days=SEASON_ARCHIVE_LAG_DAYS + 3))
    weather = await _gather(Recorder(historical=short))
    assert weather["accumulated_gdd"] is None, "a truncated archive is not a shorter season"
    assert "weather_historical_unavailable" in weather["unavailable"], "the refusal is declared"


# ── W1-10: one resolver ──


def test_resolver_prefers_gdd_and_declares_calendar_fallback():
    thermal = phenology_progress("wheat", 10, 1600.0)
    assert (thermal["stage"], thermal["stage_source"]) == ("late", "gdd"), (
        "a thermal sum inside the late band resolves to late regardless of the calendar"
    )
    calendar = phenology_progress("wheat", 10, None)
    assert (calendar["stage"], calendar["stage_source"]) == ("initial", "days"), (
        "without GDD the calendar stage is used"
    )
    assert calendar["stage_fallback"] == "calendar_days", "the fallback is declared"
    assert calendar["stage_fallback_reason"] == "accumulated_gdd_missing", "with its reason"
    past = phenology_progress("wheat", 100, 5000.0)
    assert past["stage_fallback_reason"] == "gdd_past_maturity", "past maturity is named"


def test_field_context_season_stage_uses_the_resolver():
    from api.field_context import _season_stage

    assert _season_stage("wheat", 10) == "initial", "calendar fallback without GDD"
    assert _season_stage("wheat", 10, accumulated_gdd=1600.0) == "late", (
        "with GDD the field context follows the thermal stage"
    )
    assert _season_stage("not-a-crop", 10, accumulated_gdd=1600.0) is None, (
        "an unknown crop still has no stage"
    )


def test_phenology_shape_uses_the_resolver():
    from api.routers.phenology import _shape_phenology, _shape_stage_actions

    weather = {"accumulated_gdd": 1600.0, "accumulated_gdd_through": "2026-01-15"}
    shaped = _shape_phenology("wheat", SOWING, today=SOWING + timedelta(days=10), weather=weather)
    assert shaped["current_stage"]["stage"] == "late", "/phenology follows the thermal stage"
    assert shaped["stage_source"] == "gdd", "/phenology declares its stage source"
    assert shaped["accumulated_gdd_through"] == "2026-01-15", "and the GDD coverage"
    actions = _shape_stage_actions(
        "wheat", SOWING, today=SOWING + timedelta(days=10), weather=weather
    )
    assert actions["current_stage"] == "late", "/stage-actions follows the same resolver"
    plain = _shape_phenology("wheat", SOWING, today=SOWING + timedelta(days=10))
    assert plain["stage_source"] == "days", "without weather the calendar stage is declared"
    assert plain["stage_fallback_reason"] == "accumulated_gdd_missing", "with its reason"


def test_agronomic_state_engine_uses_the_resolver():
    from core.agronomic_state_engine import CropContext, SignalInput, compose_field_state

    cs = compose_field_state(
        "F1",
        [SignalInput(source="ndvi", value=0.5)],
        crop_context=CropContext(crop_id="wheat", days_after_planting=10, accumulated_gdd=1600.0),
    )
    truths = cs.operational_truths
    assert truths["phenology_stage"] == "late", "the engine exposes the resolved thermal stage"
    assert truths["phenology_stage_source"] == "gdd", "and its source"
    cs = compose_field_state(
        "F1",
        [SignalInput(source="ndvi", value=0.5)],
        crop_context=CropContext(crop_id="wheat", days_after_planting=10),
    )
    assert cs.operational_truths["phenology_stage_source"] == "days", "calendar fallback"
