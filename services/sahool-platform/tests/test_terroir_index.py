"""Tests for terroir index: multi-factor INDICATION (low ceiling) of quality potential,
honestly declares unmeasured factors (resolves the selective-principle inconsistency)."""

from core.terroir_index import terroir_potential


class TestTerroirPotential:
    def test_ceiling_always_low(self):
        # CRITICAL: التيروير قرينة دائماً — سقف low لا high (مثل أي مدخل غير حاكم)
        r = terroir_potential(crop_id="coffee", elevation_m=2000, day_night_temp_diff_c=16)
        assert r.confidence == "low"

    def test_declares_unmeasured_gaps(self):
        # CRITICAL: يعلن ما لا يُقاس صراحةً (لا يخفيه ولا يلفّقه)
        r = terroir_potential(crop_id="coffee", elevation_m=2000)
        assert len(r.unmeasured_gaps_ar) >= 2
        assert any("الصنف" in g for g in r.unmeasured_gaps_ar)
        assert any("ميكروبيوم" in g for g in r.unmeasured_gaps_ar)

    def test_no_measured_factors_returns_none(self):
        # لا عوامل مقيسة → لا تقدير (صادق)
        r = terroir_potential(crop_id="coffee")
        assert r.potential_score is None
        assert r.confidence == "none"

    def test_high_elevation_higher_potential(self):
        low = terroir_potential(crop_id="coffee", elevation_m=400)
        high = terroir_potential(crop_id="coffee", elevation_m=2000)
        assert high.potential_score > low.potential_score

    def test_is_potential_not_judgment(self):
        # لا يدّعي حكم جودة — "إمكان" فقط
        r = terroir_potential(crop_id="coffee", elevation_m=2000, day_night_temp_diff_c=16)
        assert any("إمكان" in w or "لا حكم" in w for w in r.warnings_ar)

    def test_known_heritage_reduces_gaps(self):
        # توثيق الصنف يقلّل الفجوات المعلنة
        unknown = terroir_potential(crop_id="coffee", elevation_m=2000)
        known = terroir_potential(
            crop_id="coffee",
            elevation_m=2000,
            known_heritage_variety=True,
            known_traditional_processing=True,
        )
        assert len(known.unmeasured_gaps_ar) < len(unknown.unmeasured_gaps_ar)
