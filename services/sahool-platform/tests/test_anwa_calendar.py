"""Tests for anwa (star-rising) agricultural calendar as respected community timing indication, never governing."""

from core.anwa_calendar import ANWA_WEIGHT_CEILING, anwa_timing_context, get_star_season


class TestAnwaCalendar:
    def test_known_star_returns_season(self):
        s = get_star_season("jawza")
        assert s is not None
        assert "الذرة" in s.agricultural_meaning_ar

    def test_unknown_star_none(self):
        assert anwa_timing_context("nonexistent") is None

    def test_anwa_never_governs(self):
        # community knowledge is indication, never a hard governor
        c = anwa_timing_context("soheil")
        assert c.is_governing is False

    def test_anwa_weight_capped(self):
        c = anwa_timing_context("thuraya")
        assert c.weight <= ANWA_WEIGHT_CEILING

    def test_agreement_with_weather_strengthens(self):
        c = anwa_timing_context("soheil", weather_supports_planting=True)
        assert c.agrees_with_weather is True
        assert "تضافر" in c.note_ar or "مرجّح" in c.note_ar

    def test_disagreement_weather_takes_priority(self):
        # CRITICAL: when tradition and live weather disagree, weather wins for the decision
        c = anwa_timing_context("jawza", weather_supports_planting=False)
        assert c.agrees_with_weather is False
        assert "الطقس الآني له الأولوية" in c.note_ar

    def test_respects_tradition_in_language(self):
        # must treat tradition with respect, not dismiss it
        c = anwa_timing_context("jawza", weather_supports_planting=False)
        assert "محترم" in c.note_ar
