"""Tests for day-zero advisory: uses available data at creation, honest about limits, motivates testing."""

from core.day_zero_advisory import build_day_zero_advisory


class TestDayZeroAdvisory:
    def test_minimal_input_still_advises(self):
        # even with almost nothing, gives something + disclaimer
        adv = build_day_zero_advisory("F1", ndvi=0.3)
        assert len(adv.items) >= 1
        assert "استرشادية" in adv.disclaimer_ar

    def test_climate_is_measured_confidence(self):
        adv = build_day_zero_advisory("F1", climate={"class_ar": "حار جاف", "et0_hint": "مرتفع"})
        climate_items = [i for i in adv.items if i.topic_ar == "المناخ والطقس"]
        assert climate_items[0].confidence == "measured"

    def test_soil_texture_is_estimate(self):
        adv = build_day_zero_advisory("F1", soil_texture="رملي")
        soil_items = [i for i in adv.items if "الري" in i.topic_ar]
        assert soil_items[0].confidence == "estimate"
        assert soil_items[0].upgrade_ar  # must say what raises precision

    def test_district_context_never_field_value(self):
        # CRITICAL: district salinity is context, never the farmer's field value
        adv = build_day_zero_advisory("F1", district_salinity_context=4.2)
        ctx_items = [i for i in adv.items if "الملوحة" in i.topic_ar]
        assert ctx_items[0].confidence == "district_context"
        assert "ليس قيمة حقلك" in ctx_items[0].advice_ar

    def test_pesticides_always_blocked(self):
        adv = build_day_zero_advisory("F1", ndvi=0.5)
        pest_items = [i for i in adv.items if "مبيد" in i.topic_ar]
        assert len(pest_items) == 1
        assert "محجوبة" in pest_items[0].advice_ar

    def test_lists_missing_for_precision(self):
        adv = build_day_zero_advisory("F1", ndvi=0.4)
        # must always tell farmer what raises precision
        assert any("ملوحة" in m for m in adv.missing_for_precision_ar)
        assert any("pH" in m for m in adv.missing_for_precision_ar)

    def test_always_has_motivating_next_steps(self):
        adv = build_day_zero_advisory("F1", ndvi=0.4)
        assert len(adv.next_steps_ar) >= 1
        assert any("تحليل" in s for s in adv.next_steps_ar)

    def test_crop_suitability_provisional_only(self):
        adv = build_day_zero_advisory("F1", soil_texture="طيني", crop_id="قمح")
        crop_items = [i for i in adv.items if "ملاءمة المحصول" in i.topic_ar]
        assert crop_items[0].confidence == "estimate"
