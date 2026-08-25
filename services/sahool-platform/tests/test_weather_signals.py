"""اختبارات توليد إشارات الطقس + المُجمِّع (core/weather_signals) — نقيّ."""

from __future__ import annotations

import pytest
from core.weather_overlay import FieldWeatherScores
from core.weather_signals import aggregate_cells_to_hourly, generate_signals

pytestmark = pytest.mark.unit


def _scores(**kw):
    base = dict(
        spray_suitability_score=0.0,
        disease_risk_score=0.0,
        trafficability_score=100.0,
        heat_stress_hours=0,
        frost_risk_hours=0,
        hours_evaluated=24,
        # المقامان المخصوصان: الفرصُ القابلة لرصد كلّ حدث (P4).
        frost_evaluable_hours=24,
        heat_evaluable_hours=24,
    )
    base.update(kw)
    return FieldWeatherScores(**base)


class TestSignals:
    def test_no_signals_when_benign(self):
        assert generate_signals(_scores()) == []

    def test_spray_window_open(self):
        sig = generate_signals(_scores(spray_suitability_score=0.7))
        assert any(s.signal_type == "spray_window_open" and s.confidence_score == 0.7 for s in sig)

    def test_disease_alert(self):
        sig = generate_signals(_scores(disease_risk_score=0.8))
        assert any(s.signal_type == "disease_risk_high" for s in sig)

    def test_frost_and_heat(self):
        sig = generate_signals(_scores(frost_risk_hours=6, heat_stress_hours=3))
        types = {s.signal_type for s in sig}
        assert "frost_imminent" in types and "heat_stress" in types

    def test_trafficability_poor(self):
        sig = generate_signals(_scores(trafficability_score=10.0))
        s = next(s for s in sig if s.signal_type == "trafficability_poor")
        assert s.confidence_score == 0.9  # 1 - 10/100

    def test_an_incoherent_count_yields_no_signal_rather_than_full_confidence(self):
        """كان هذا الاختبار يُثبِّت العطل: ``frost_hours=50, hours_evaluated=24`` تُقَصّ
        إلى **1.0** — أي يُترجَم عدٌّ مستحيل (ساعاتُ صقيعٍ أكثرُ من الساعات المرصودة)
        إلى **أقوى** جملةِ ثقة ممكنة. والصمتُ أصدق: مدخلٌ متناقض لا يُنتِج إشارة."""
        sig = generate_signals(_scores(frost_risk_hours=50, hours_evaluated=24))
        assert not [s for s in sig if s.signal_type == "frost_imminent"]


class TestAggregate:
    def test_aggregates_cells_per_hour(self):
        rows = [
            {"hour": 1, "temp_avg": 20, "temp_min": 18, "temp_max": 25, "precip_sum": 0.0},
            {"hour": 1, "temp_avg": 22, "temp_min": 19, "temp_max": 27, "precip_sum": 1.0},
            {"hour": 2, "temp_avg": 24, "temp_min": 20, "temp_max": 30, "precip_sum": 0.0},
        ]
        hourly = aggregate_cells_to_hourly(rows)
        assert len(hourly) == 2  # ساعتان مميّزتان
        h1 = hourly[0]
        assert h1.temp_avg_c == 21  # متوسّط 20,22
        assert h1.temp_min_c == 18 and h1.temp_max_c == 27  # أدنى الأدنى، أقصى الأقصى
        assert h1.precip_mm == 0.5  # متوسّط 0,1

    def test_empty_rows(self):
        assert aggregate_cells_to_hourly([]) == []
