"""Tests for measurement principle: unit harmonization (reject ambiguous local units)
and spatial decay (neighbor validity by correlation length). Soil≠Water."""

from core.measurement import harmonize_unit, spatial_substitution_validity


class TestUnitHarmonization:
    def test_rejects_ambiguous_local_unit(self):
        # CRITICAL: لتر/فدان بلا مساحة → مرفوض (لا يمكن المقارنة)
        r = harmonize_unit(500, "لتر/فدان")
        assert not r.ok
        assert r.value is None

    def test_dsm_mscm_are_one_to_one(self):
        # CRITICAL: 1 dS/m = 1 mS/cm (الوثيقة قالت 10 — خطأ علمي صُحّح)
        r = harmonize_unit(3.5, "mS/cm")
        assert r.ok
        assert r.value == 3.5  # ليس 35

    def test_ton_ha_to_kg_ha(self):
        r = harmonize_unit(6.2, "ton/ha")
        assert r.ok
        assert r.value == 6200.0

    def test_canonical_unit_passes(self):
        r = harmonize_unit(5.0, "dS/m")
        assert r.ok and r.value == 5.0

    def test_untraceable_rejected(self):
        r = harmonize_unit(1, "صاع")
        assert not r.ok


class TestSpatialDecay:
    def test_water_neighbor_85m_accepted(self):
        # ماء الجار 85م ضمن L=2000م → مقبول (medium)
        v = spatial_substitution_validity("water_ec", 85)
        assert v.valid
        assert v.confidence_ceiling == "medium"

    def test_soil_n_neighbor_85m_rejected(self):
        # CRITICAL: تربة الجار 85م تتجاوز L=50م → مرفوض (NONE)
        v = spatial_substitution_validity("soil_n", 85)
        assert not v.valid
        assert v.confidence_ceiling == "none"

    def test_soil_ph_high_variance_rejected_at_85m(self):
        v = spatial_substitution_validity("soil_ph", 85)
        assert not v.valid

    def test_weather_long_range_valid(self):
        # الطقس L=10كم → 5كم مقبول
        v = spatial_substitution_validity("weather", 5000)
        assert v.valid

    def test_beyond_correlation_length_rejected(self):
        # تجاوز طول الارتباط → مرفوض دائماً
        v = spatial_substitution_validity("water_ec", 3000)  # > 2000
        assert not v.valid

    def test_soil_capped_at_low_even_when_close(self):
        # التربة لا تتجاوز low حتى لو قريبة جداً (تباين دقيق)
        v = spatial_substitution_validity("soil_n", 10)  # ضمن 50م
        assert v.valid
        assert v.confidence_ceiling == "low"

    def test_unknown_type_rejected(self):
        v = spatial_substitution_validity("unknown_xyz", 10)
        assert not v.valid
