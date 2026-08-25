"""حُرّاس مخاطر الطقس حسب المرحلة (Stage-aware Risk) — منطق نقيّ."""

from __future__ import annotations

from datetime import date, timedelta

from core.crop_cards.loader import load_crop_card
from core.season_stage_risk import critical_window_collisions, stage_weather_risks


def _codes(res):
    return {r["code"] for r in res["risks"]}


class TestFloweringStage:
    def test_flowering_heat_uses_crop_card_threshold(self):
        # قمح: عتبة تزهير 31°م. tmax=34 ⇒ عقم لقاح (high).
        res = stage_weather_risks("mid", "wheat", {"tmax_c": 34})
        assert "flowering_heat_sterility" in _codes(res)
        assert res["overall_severity"] == "high"
        assert res["requires_action"] is True

    def test_maize_higher_threshold_not_triggered_at_34(self):
        # ذرة شاميّة: عتبة 35°م. tmax=34 ⇒ لا عقم (أعلى تحمّلاً من القمح).
        res = stage_weather_risks("mid", "maize", {"tmax_c": 34})
        assert "flowering_heat_sterility" not in _codes(res)

    def test_flowering_water_stress_is_high(self):
        res = stage_weather_risks("mid", "wheat", {"water_stress_factor": 0.5})
        assert "flowering_water" in _codes(res)
        assert res["overall_severity"] == "high"

    def test_flowering_wind(self):
        res = stage_weather_risks("mid", "wheat", {"wind_kmh": 35})
        assert "flowering_wind" in _codes(res)


class TestEstablishmentStage:
    def test_frost_at_germination(self):
        res = stage_weather_risks("initial", "wheat", {"tmin_c": 1.0})
        assert "establishment_frost" in _codes(res)
        assert res["overall_severity"] == "high"

    def test_establishment_water_stress(self):
        res = stage_weather_risks("initial", "wheat", {"water_deficit_mm": 40})
        assert "establishment_water" in _codes(res)


class TestHarvestStage:
    def test_harvest_rain_risk(self):
        res = stage_weather_risks("late", "wheat", {"rain_mm_next_7d": 30})
        assert "harvest_rain" in _codes(res)
        assert res["overall_severity"] == "high"

    def test_grainfill_water_deficit(self):
        res = stage_weather_risks("late", "wheat", {"water_stress_factor": 0.6})
        assert "grainfill_water" in _codes(res)

    def test_harvest_humidity(self):
        res = stage_weather_risks("late", "wheat", {"rh_pct": 85})
        assert "harvest_humidity" in _codes(res)


class TestHonesty:
    def test_no_stage_returns_low_confidence_no_risk(self):
        res = stage_weather_risks(None, "wheat", {"tmax_c": 40})
        assert res["risks"] == [] and res["confidence"] == "low"
        assert "current_stage" in res["evidence_missing"]

    def test_missing_signals_flagged_and_lower_confidence(self):
        # mid يهمّه tmax/ماء/رياح؛ لا شيء مُرسَل ⇒ evidence_missing + confidence low.
        res = stage_weather_risks("mid", "wheat", {})
        assert res["risks"] == []
        assert set(res["evidence_missing"]) >= {"tmax_c", "water_stress_factor", "wind_kmh"}
        assert res["confidence"] == "low"

    def test_confidence_never_high(self):
        res = stage_weather_risks(
            "mid", "wheat", {"tmax_c": 34, "water_stress_factor": 0.5, "wind_kmh": 35}
        )
        assert res["confidence"] in ("low", "medium")
        assert res["confidence"] != "high"  # الطقس متوقّع لا مضمون

    def test_no_risks_when_benign(self):
        res = stage_weather_risks(
            "mid", "wheat", {"tmax_c": 25, "water_stress_factor": 1.0, "wind_kmh": 5}
        )
        assert res["risks"] == [] and res["overall_severity"] == "none"
        assert res["requires_action"] is False

    def test_unknown_crop_uses_conservative_default_threshold(self):
        # محصول بلا بطاقة ⇒ عتبة تزهير احتياطيّة 32°م (مُعلَّمة)، لا تعطّل التقييم.
        res = stage_weather_risks("mid", "nonexistent", {"tmax_c": 33})
        assert "flowering_heat_sterility" in _codes(res)


class TestCriticalWindowCollisions:
    """W2 — المصادم: نافذةٌ حرجة متوقَّعة × تنبؤٌ يوميّ ⇒ حدثٌ بزمنٍ قياديّ.

    ذرة شاميّة: عتبة التزهير 35°م من البطاقة (لا ثابتٌ مكتوبٌ هنا).
    """

    TODAY = date(2026, 8, 1)

    def _window(self, **over):
        base = {
            "status": "upcoming",
            "stage": "mid",
            "start_date": "2026-08-11",
            "end_date": "2026-08-20",
            "lead_days": 10,
            "source": "gdd_forecast",
            "confidence": "medium",
            "evidence_missing": [],
        }
        base.update(over)
        return base

    def _forecast(self, hot_days=(), tmax_hot=38.0, tmax_cool=30.0, days=30):
        return [
            {
                "date": (self.TODAY + timedelta(days=i)).isoformat(),
                "tmax_c": tmax_hot if i in hot_days else tmax_cool,
            }
            for i in range(1, days + 1)
        ]

    def test_a_collision_inside_the_window_carries_lead_time_and_the_card_threshold(self):
        out = critical_window_collisions(
            "maize", self._window(), self._forecast(hot_days=(12, 13)), today=self.TODAY
        )
        assert out["status"] == "collisions"
        assert [e["lead_days"] for e in out["events"]] == [12, 13]
        card_threshold = load_crop_card("maize")["thermal"]["flowering_safe_max_c"]
        assert all(e["threshold_c"] == card_threshold for e in out["events"])
        assert out["threshold_source"] == "crop_card.thermal.flowering_safe_max_c"

    def test_heat_outside_the_window_is_not_an_event(self):
        """الخاصّيّة الجوهريّة: الخطر خارج النافذة ليس خطراً على هذا الطور.

        لولاها لصار المنتَج «إنذارَ طقسٍ حارّ» عامّاً — وهو ما تملكه المنصّة أصلاً.
        """
        before = self._forecast(hot_days=tuple(range(1, 10)), tmax_hot=45.0)
        after = self._forecast(hot_days=tuple(range(21, 31)), tmax_hot=45.0)
        assert (
            critical_window_collisions("maize", self._window(), before, today=self.TODAY)["status"]
            == "clear"
        )
        assert (
            critical_window_collisions("maize", self._window(), after, today=self.TODAY)["status"]
            == "clear"
        )

    def test_a_passed_or_unknown_window_is_not_applicable(self):
        for window in (None, {"status": "past"}, {"status": "insufficient_context"}):
            out = critical_window_collisions("maize", window, self._forecast(), today=self.TODAY)
            assert out["status"] == "not_applicable"
            assert out["events"] == []

    def test_no_forecast_is_insufficient_context_not_a_denial_of_risk(self):
        out = critical_window_collisions("maize", self._window(), None, today=self.TODAY)
        assert out["status"] == "insufficient_context"
        assert "forecast_daily_missing" in out["evidence_missing"]

    def test_severity_scales_with_exceedance_not_with_temperature_alone(self):
        mild = critical_window_collisions(
            "maize", self._window(), self._forecast(hot_days=(12,), tmax_hot=36.0), today=self.TODAY
        )
        severe = critical_window_collisions(
            "maize", self._window(), self._forecast(hot_days=(12,), tmax_hot=40.0), today=self.TODAY
        )
        assert mild["events"][0]["severity"] == "medium"
        assert severe["events"][0]["severity"] == "high"
        assert severe["events"][0]["exceedance_c"] > mild["events"][0]["exceedance_c"]

    def test_the_threshold_follows_the_crop_not_a_hardcoded_number(self):
        # قمح 31°م: 33°م تصادمٌ له وليست تصادماً للذرة (35°م).
        forecast = self._forecast(hot_days=(12,), tmax_hot=33.0)
        wheat = critical_window_collisions("wheat", self._window(), forecast, today=self.TODAY)
        maize = critical_window_collisions("maize", self._window(), forecast, today=self.TODAY)
        assert wheat["status"] == "collisions"
        assert maize["status"] == "clear"

    def test_confidence_is_inherited_and_never_exceeds_its_window(self):
        """تصادمٌ مبنيٌّ على نافذةٍ تقويميّة لا يصير أوثقَ من نافذته."""
        low = critical_window_collisions(
            "maize",
            self._window(source="calendar_fallback", confidence="low"),
            self._forecast(hot_days=(12,)),
            today=self.TODAY,
        )
        assert low["confidence"] == "low"
        assert low["status"] == "collisions"  # يُبلِّغ ولا يُخفي، لكن بثقته لا بأعلى

    def test_uncalibrated_thresholds_are_declared_in_the_output(self):
        out = critical_window_collisions(
            "maize", self._window(), self._forecast(hot_days=(12,)), today=self.TODAY
        )
        assert out["calibration"] == "uncalibrated"

    def test_a_horizon_shorter_than_the_window_is_declared_not_extrapolated(self):
        short = self._forecast(days=12)  # النافذة تنتهي +19 يوماً
        out = critical_window_collisions("maize", self._window(), short, today=self.TODAY)
        assert "window_end_beyond_forecast_horizon" in out["evidence_missing"]

    def test_a_window_with_no_tmax_inside_it_says_so(self):
        blind = [
            {"date": (self.TODAY + timedelta(days=i)).isoformat(), "tmax_c": None}
            for i in range(1, 31)
        ]
        out = critical_window_collisions("maize", self._window(), blind, today=self.TODAY)
        assert out["status"] == "clear"
        assert "tmax_missing_inside_window" in out["evidence_missing"]
