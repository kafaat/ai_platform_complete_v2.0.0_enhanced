"""v26 workstream 04: weather-engine GDD absence is not a harvested zero."""

import pytest
from api.season_simulation import DayWeather, SimContext, simulate_season

WEATHER = [DayWeather(t_min_c=10, t_max_c=25, et0_mm=4) for _ in range(20)]


def _sim(crop, gdd, **kw):
    return simulate_season(SimContext(crop=crop, weather=WEATHER, gdd_daily_override=gdd, **kw))


@pytest.mark.unit
@pytest.mark.parametrize("crop", ["wheat", "قمح", "Wheat"])
@pytest.mark.parametrize("gdd", [None, [None] * 20])
def test_missing_entire_gdd_series_is_unavailable_not_zero(crop, gdd):
    result = _sim(crop, gdd)
    assert result.crop_recognized
    assert (result.yield_kg_ha, result.yield_low_kg_ha, result.yield_high_kg_ha) == (
        None,
        None,
        None,
    )
    assert result.yield_status == "unavailable_missing_gdd"
    assert "NO_GDD_EVIDENCE_NO_YIELD_ESTIMATE" in result.limitations
    assert result.confidence == 0


@pytest.mark.unit
def test_partial_gdd_is_explicit_and_less_confident():
    full = _sim("wheat", [18.0] * 20)
    partial = _sim("wheat", [18.0] * 10 + [None] * 10)
    assert full.yield_kg_ha is not None and full.yield_kg_ha > 0
    assert full.yield_status == "estimated" and "PARTIAL_GDD_EVIDENCE" not in full.limitations
    assert partial.yield_kg_ha is not None
    assert partial.confidence < full.confidence
    assert "PARTIAL_GDD_EVIDENCE" in partial.limitations


@pytest.mark.unit
def test_observed_fapar_keeps_its_yield_but_declares_unknown_maturity():
    result = _sim("wheat", None, observed_fapar=0.6)
    assert result.yield_kg_ha is not None and result.yield_kg_ha > 0
    assert "NO_GDD_EVIDENCE_MATURITY_UNKNOWN" in result.limitations
    assert result.maturity_reached is False


@pytest.mark.unit
def test_unsupported_crop_stays_unrecognized_whatever_the_gdd():
    for gdd in (None, [18.0] * 20):
        result = _sim("dragonfruit", gdd)
        assert result.yield_kg_ha is None
        assert result.yield_status == "unavailable_unrecognized_crop"


@pytest.mark.unit
def test_no_weather_is_unavailable_not_zero():
    result = simulate_season(SimContext(crop="wheat", weather=[]))
    assert result.yield_kg_ha is None
    assert result.yield_status == "unavailable_no_weather"
    assert "NO_WEATHER_NO_YIELD_ESTIMATE" in result.limitations
