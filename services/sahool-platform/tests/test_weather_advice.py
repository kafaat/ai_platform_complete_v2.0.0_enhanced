"""اختبارات منطق توصية الريّ ومخاطر الأمراض (api.weather_advice) — أجزاء صرفة.

يغطّي: resolve_kc (محصول مُعرّف/عامّ)، irrigation_advice (الاحتياج الصافي،
الإلحاح، أثر المطر/رطوبة التربة)، disease_risk (تجميع العوامل + كبح الحرارة).
لا حاجة لقاعدة أو شبكة — منطق نقيّ بالكامل.
"""

from api.water_balance import KC_BY_CROP_STAGE
from api.weather_advice import disease_risk, irrigation_advice, resolve_kc


class TestResolveKc:
    def test_known_crop_uses_fao_table(self):
        kc, known, source = resolve_kc("wheat", "mid")
        assert known is True
        assert kc == KC_BY_CROP_STAGE["wheat"]["mid"]
        assert "FAO-56" in source

    def test_case_insensitive_and_trimmed(self):
        kc, known, _ = resolve_kc("  Wheat  ", "mid")
        assert known is True
        assert kc == KC_BY_CROP_STAGE["wheat"]["mid"]

    def test_unknown_crop_falls_back_and_is_flagged(self):
        kc, known, source = resolve_kc("dragonfruit", "mid")
        assert known is False
        assert kc == 1.1  # منحنى عامّ mid
        assert "عامّ" in source

    def test_none_crop_is_generic(self):
        _kc, known, _ = resolve_kc(None, "initial")
        assert known is False


class TestIrrigationAdvice:
    def test_returns_required_keys(self):
        r = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid")
        for k in ("recommended_mm", "urgency", "timing_ar", "et0", "kc", "rationale_ar"):
            assert k in r

    def test_etc_drives_recommendation(self):
        # ET0=6, Kc(wheat,mid)=1.15 ⇒ ETc≈6.9، بلا مطر ⇒ recommended≈6.9
        r = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid", rain_recent_mm=0.0)
        assert r["recommended_mm"] > 6.0
        assert r["kc"] == 1.15
        assert r["urgency"] == "moderate"  # 4 ≤ net < 8

    def test_high_demand_is_high_urgency(self):
        r = irrigation_advice(et0_mm=10.0, crop="maize", stage="mid")
        assert r["urgency"] == "high"
        assert "اليوم" in r["timing_ar"]

    def test_rain_covers_demand_no_irrigation(self):
        r = irrigation_advice(et0_mm=3.0, crop="wheat", stage="initial", rain_recent_mm=40.0)
        assert r["recommended_mm"] == 0.0
        assert r["urgency"] == "none"
        assert "لا حاجة" in r["rationale_ar"]

    def test_forecast_rain_defers_irrigation(self):
        base = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid")
        deferred = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid", forecast_rain_mm=12.0)
        # نفس الاحتياج لكن الإلحاح يهبط بسبب المطر المتوقّع.
        assert base["urgency"] == "moderate"
        assert deferred["urgency"] == "low"

    def test_critical_soil_moisture_forces_high(self):
        r = irrigation_advice(et0_mm=5.0, crop="wheat", stage="mid", soil_moisture_pct=20.0)
        assert r["urgency"] == "high"

    def test_comfortable_soil_moisture_lowers_urgency(self):
        r = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid", soil_moisture_pct=70.0)
        assert r["urgency"] == "low"

    def test_negative_et0_clamped(self):
        r = irrigation_advice(et0_mm=-3.0, crop="wheat", stage="mid")
        assert r["et0"] == 0.0
        assert r["recommended_mm"] == 0.0


class TestDiseaseRisk:
    def test_returns_required_keys(self):
        r = disease_risk(temp_c=22.0, humidity_pct=85.0, rain_mm_3d=12.0)
        for k in ("risk_level", "diseases_ar", "advice_ar"):
            assert k in r

    def test_humid_mild_wet_is_high_risk(self):
        r = disease_risk(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0)
        assert r["risk_level"] == "high"
        assert r["diseases_ar"]  # غير فارغة

    def test_dry_hot_is_low_risk(self):
        r = disease_risk(temp_c=40.0, humidity_pct=20.0, rain_mm_3d=0.0)
        assert r["risk_level"] == "low"
        assert r["diseases_ar"] == []

    def test_two_factors_is_moderate(self):
        # رطوبة عالية + حرارة معتدلة، بلا مطر تراكميّ ⇒ عاملان ⇒ moderate
        r = disease_risk(temp_c=22.0, humidity_pct=85.0, rain_mm_3d=0.0)
        assert r["risk_level"] == "moderate"

    def test_high_heat_suppresses_score(self):
        # رطوبة عالية + مطر، لكن حرارة > 35 تكبح عاملاً ⇒ لا يصل high
        r = disease_risk(temp_c=38.0, humidity_pct=90.0, rain_mm_3d=20.0)
        assert r["risk_level"] in {"low", "moderate"}

    def test_diseases_deduplicated(self):
        r = disease_risk(temp_c=20.0, humidity_pct=90.0, rain_mm_3d=15.0)
        assert len(r["diseases_ar"]) == len(set(r["diseases_ar"]))
