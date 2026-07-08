"""حُرّاس مخاطر الطقس حسب المرحلة (Stage-aware Risk) — منطق نقيّ."""

from __future__ import annotations

from core.season_stage_risk import stage_weather_risks


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
