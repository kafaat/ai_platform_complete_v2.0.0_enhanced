"""Tests for soil-property → recommendation chains (texture→irrigation, pH→fertilizer, texture→crop bias)."""
from core.soil_recommendations import (
    fertilizer_hint_from_ph, irrigation_hint_from_texture,
    crop_bias_from_texture, soil_to_recommendations)


class TestFertilizerFromPH:
    def test_ph_none_requires_lab(self):
        h = fertilizer_hint_from_ph(None)
        assert h.requires_lab is True
        assert h.ph_class == "غير معروف"

    def test_acidic_ph(self):
        h = fertilizer_hint_from_ph(5.5)
        assert h.ph_class == "حمضي"
        assert any("جير" in x for x in h.hints_ar)

    def test_alkaline_ph(self):
        h = fertilizer_hint_from_ph(8.5)
        assert h.ph_class == "قلوي"
        assert any("جبس" in x or "كبريت" in x for x in h.hints_ar)

    def test_neutral_ph(self):
        h = fertilizer_hint_from_ph(7.0)
        assert h.ph_class == "متعادل"


class TestIrrigationFromTexture:
    def test_sandy_frequent_small(self):
        h = irrigation_hint_from_texture("رملي (تقديري)")
        assert "متكرّر" in h.pattern_ar

    def test_clay_less_frequent(self):
        h = irrigation_hint_from_texture("طيني (تقديري)")
        assert "أقل تكراراً" in h.pattern_ar

    def test_unknown_texture_none(self):
        assert irrigation_hint_from_texture("صخري") is None


class TestCropBias:
    def test_sandy_favors_trees(self):
        b = crop_bias_from_texture("رملي")
        assert any("أشجار" in x or "جذرية" in x for x in b.favored_ar)

    def test_clay_favors_grains(self):
        b = crop_bias_from_texture("طيني")
        assert any("قمح" in x or "حبوب" in x for x in b.favored_ar)

    def test_bias_always_carries_warning(self):
        # CRITICAL: texture-based crop suggestion must always warn it's not the final decision
        for tex in ("رملي", "طيني", "طميي"):
            b = crop_bias_from_texture(tex)
            assert "عامل واحد" in b.warning_ar or "القرار النهائي" in b.warning_ar


class TestIntegration:
    def test_full_chain_sandy_alkaline(self):
        r = soil_to_recommendations("رملي (تقديري)", soil_ph=8.5)
        assert r["irrigation"] is not None
        assert r["fertilizer"]["ph_class"] == "قلوي"
        assert r["crop_bias"] is not None

    def test_fertilizer_blocked_without_ph(self):
        r = soil_to_recommendations("طيني", soil_ph=None)
        assert r["fertilizer"]["requires_lab"] is True
