"""Tests for tiered collective learning: aware farmers help low-data farmers WITHOUT fabricating field values."""
from core.district_baseline import (
    compute_district_baseline, context_for_low_data_farmer, MIN_FARMS_FOR_BASELINE)


class TestDistrictBaseline:
    def test_empty_district_not_usable(self):
        bl = compute_district_baseline("d1", "S3", [])
        assert not bl.is_usable
        assert bl.n_farms == 0

    def test_below_threshold_not_usable(self):
        bl = compute_district_baseline("d1", "S3", [4.0, 4.2, 4.1])  # 3 < 5
        assert not bl.is_usable
        assert bl.confidence == "low"

    def test_sufficient_farms_usable(self):
        bl = compute_district_baseline("d1", "S3", [3.8, 4.1, 4.5, 4.0, 4.3, 4.6])
        assert bl.is_usable
        assert bl.n_farms == 6
        assert bl.median_value is not None

    def test_homogeneous_district_medium_confidence(self):
        # tight spread → medium confidence
        bl = compute_district_baseline("d1", "S3", [4.0, 4.1, 4.0, 4.2, 4.1])
        assert bl.confidence == "medium"

    def test_heterogeneous_district_low_confidence(self):
        # wide spread → low confidence (district not uniform)
        bl = compute_district_baseline("d1", "S3", [1.0, 8.0, 2.0, 7.0, 4.0])
        assert bl.confidence == "low"


class TestFarmerContext:
    def test_context_never_claims_field_value(self):
        # CRITICAL HONESTY: must never present district avg as the farmer's field value
        bl = compute_district_baseline("d1", "S3", [3.8, 4.1, 4.5, 4.0, 4.3, 4.6])
        ctx = context_for_low_data_farmer(bl, "ملوحة التربة")
        assert ctx.is_field_specific is False
        assert "ليس قيمة حقلك" in ctx.context_ar or "سياق" in ctx.context_ar

    def test_low_data_farmer_still_blocked_precise(self):
        # collective context does NOT unblock precise recommendations
        bl = compute_district_baseline("d1", "S3", [3.8, 4.1, 4.5, 4.0, 4.3, 4.6])
        ctx = context_for_low_data_farmer(bl, "ملوحة التربة")
        assert ctx.blocks_precise is True

    def test_always_motivates_testing(self):
        bl = compute_district_baseline("d1", "S3", [3.8, 4.1, 4.5, 4.0, 4.3, 4.6])
        ctx = context_for_low_data_farmer(bl, "ملوحة التربة")
        assert "حلّل" in ctx.motivation_ar

    def test_insufficient_baseline_encourages_first_mover(self):
        bl = compute_district_baseline("d1", "S3", [4.0])
        ctx = context_for_low_data_farmer(bl, "ملوحة التربة")
        assert "أوّل" in ctx.motivation_ar or "جيران" in ctx.motivation_ar
