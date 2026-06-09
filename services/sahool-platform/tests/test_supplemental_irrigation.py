"""Tests for supplemental irrigation (rainfed highland Yemen — 70% of agriculture).
Different from deficit_irrigation: rainfed needs supplementation, not deficit management."""

from core.engines.supplemental_irrigation import compute_water_gap, seasonal_summary


class TestWaterGap:
    def test_rain_meets_demand_no_supplemental(self):
        # المطر يلبّي الاحتياج → لا حاجة لريّ تكميلي
        g = compute_water_gap(etc_mm=100, rainfall_mm=120, growth_stage="vegetative")
        assert not g.needs_supplemental
        assert g.gap_mm <= 0

    def test_critical_stage_gap_triggers_supplemental(self):
        # CRITICAL: مرحلة حرجة (الإزهار) + فجوة → ريّ تكميلي مطلوب
        g = compute_water_gap(etc_mm=120, rainfall_mm=50, growth_stage="flowering")
        assert g.needs_supplemental
        assert g.recommended_mm is not None
        assert g.recommended_mm > 0
        # ملء جزئي ~70% من الفجوة (لا ريّ كامل — يحافظ على فلسفة الكفاءة)
        assert g.recommended_mm < (g.etc_mm - g.rainfall_mm)

    def test_small_gap_no_supplemental(self):
        # فجوة طفيفة <20% → لا حاجة
        g = compute_water_gap(etc_mm=100, rainfall_mm=85, growth_stage="vegetative")
        assert not g.needs_supplemental

    def test_non_critical_stage_moderate_gap_optional(self):
        # فجوة معتبرة في مرحلة غير حرجة → اختياري لا مطلوب
        g = compute_water_gap(etc_mm=100, rainfall_mm=70, growth_stage="vegetative")
        assert not g.needs_supplemental  # 30% فجوة + مرحلة غير حرجة

    def test_flowering_highest_sensitivity(self):
        # الإزهار يحمل أعلى حسّاسية (Ky=1.10)
        g = compute_water_gap(etc_mm=100, rainfall_mm=70, growth_stage="flowering")
        assert g.stage_sensitivity >= 1.0
        assert g.needs_supplemental

    def test_maturity_low_sensitivity(self):
        # النضج لا يحتاج ريّاً (Ky=0.30)
        g = compute_water_gap(etc_mm=100, rainfall_mm=30, growth_stage="maturity")
        assert g.stage_sensitivity <= 0.40

    def test_zero_etc_returns_none(self):
        g = compute_water_gap(etc_mm=0, rainfall_mm=50, growth_stage="vegetative")
        assert g.confidence == "none"

    def test_soil_storage_reduces_gap(self):
        # مخزون التربة يقلّل الفجوة
        without = compute_water_gap(etc_mm=100, rainfall_mm=50, growth_stage="flowering")
        with_storage = compute_water_gap(
            etc_mm=100, rainfall_mm=50, growth_stage="flowering", soil_water_storage_mm=30
        )
        assert with_storage.gap_mm < without.gap_mm

    def test_carries_estimate_warning(self):
        g = compute_water_gap(etc_mm=100, rainfall_mm=50, growth_stage="flowering")
        assert any("تقدير" in w for w in g.warnings_ar)


class TestSeasonalSummary:
    def test_summary_aggregates_gaps(self):
        gaps = [
            compute_water_gap(etc_mm=80, rainfall_mm=100, growth_stage="vegetative"),
            compute_water_gap(etc_mm=120, rainfall_mm=40, growth_stage="flowering"),
            compute_water_gap(etc_mm=100, rainfall_mm=60, growth_stage="grain_fill"),
        ]
        s = seasonal_summary(gaps)
        assert s["months_needing_supplemental"] >= 1
        assert s["total_supplemental_recommended_mm"] > 0
