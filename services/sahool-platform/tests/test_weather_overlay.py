"""اختبارات منطق تراكب الطقس (core/weather_overlay) — نقيّ، عتبات قراريّة."""

from __future__ import annotations

import pytest
from core.weather_overlay import HourlyWeather, compute_scores

pytestmark = pytest.mark.unit


def _h(**kw):
    return HourlyWeather(**kw)


class TestSpray:
    def test_all_sprayable(self):
        hours = [_h(delta_t_c=4, wind_speed_ms=2.0, precip_mm=0.0) for _ in range(5)]
        assert compute_scores(hours).spray_suitability_score == 1.0

    def test_wind_too_high_blocks(self):
        hours = [_h(delta_t_c=4, wind_speed_ms=10.0, precip_mm=0.0) for _ in range(5)]
        assert compute_scores(hours).spray_suitability_score == 0.0

    def test_inversion_low_delta_t_blocks(self):
        hours = [_h(delta_t_c=0.5, wind_speed_ms=2.0, precip_mm=0.0) for _ in range(4)]
        assert compute_scores(hours).spray_suitability_score == 0.0

    def test_rain_blocks(self):
        hours = [_h(delta_t_c=4, wind_speed_ms=2.0, precip_mm=1.0) for _ in range(4)]
        assert compute_scores(hours).spray_suitability_score == 0.0

    def test_mixed_fraction(self):
        ok = _h(delta_t_c=4, wind_speed_ms=2.0, precip_mm=0.0)
        bad = _h(delta_t_c=4, wind_speed_ms=12.0, precip_mm=0.0)
        assert compute_scores([ok, ok, bad, bad]).spray_suitability_score == 0.5


class TestDisease:
    def test_high_humidity_warm_is_risk(self):
        hours = [_h(humidity_pct=90, temp_avg_c=20) for _ in range(4)]
        assert compute_scores(hours).disease_risk_score == 1.0

    def test_dry_is_no_risk(self):
        hours = [_h(humidity_pct=40, temp_avg_c=20) for _ in range(4)]
        assert compute_scores(hours).disease_risk_score == 0.0

    def test_too_cold_no_risk(self):
        hours = [_h(humidity_pct=95, temp_avg_c=5) for _ in range(4)]
        assert compute_scores(hours).disease_risk_score == 0.0


class TestTrafficabilityAndStress:
    def test_no_rain_full_trafficability(self):
        hours = [_h(precip_mm=0.0) for _ in range(10)]
        assert compute_scores(hours).trafficability_score == 100.0

    def test_heavy_rain_low_trafficability(self):
        hours = [_h(precip_mm=20.0) for _ in range(10)]  # 200mm tot ≫ cap 40 ⇒ ~0
        assert compute_scores(hours).trafficability_score < 1.0

    def test_heat_and_frost_hours(self):
        hours = [
            _h(temp_max_c=42, temp_min_c=10),
            _h(temp_max_c=30, temp_min_c=1),
            _h(temp_max_c=39, temp_min_c=0),
        ]
        s = compute_scores(hours)
        assert s.heat_stress_hours == 2  # 42, 39 > 38
        assert s.frost_risk_hours == 2  # 1, 0 < 2

    def test_empty_is_neutral(self):
        s = compute_scores([])
        assert s.hours_evaluated == 0
        assert s.spray_suitability_score == 0.0 and s.trafficability_score == 0.0
