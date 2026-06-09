"""tests/test_crop_portfolio.py — اختبارات تأثير المحفظة."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.crop_portfolio import (
    FieldAllocation,
    compare_portfolios,
    compute_portfolio_metrics,
    format_metrics_ar,
    suggest_for_portfolio,
)


class TestCropPortfolio:
    def test_monoculture_detected(self):
        """٩٥٪+ محصول واحد → monoculture."""
        allocs = [
            FieldAllocation("f1", "wheat", 95.0),
            FieldAllocation("f2", "barley", 5.0),
        ]
        m = compute_portfolio_metrics(allocs)
        assert m.classification == "monoculture"
        assert m.dominance_pct >= 95
        assert m.crop_count == 2
        assert m.effective_crop_number < 1.5

    def test_high_diversity(self):
        """٤ محاصيل متساوية → ENC ≈ 4."""
        allocs = [
            FieldAllocation("f1", "wheat", 25.0),
            FieldAllocation("f2", "barley", 25.0),
            FieldAllocation("f3", "sorghum", 25.0),
            FieldAllocation("f4", "millet", 25.0),
        ]
        m = compute_portfolio_metrics(allocs)
        assert abs(m.effective_crop_number - 4.0) < 0.01
        assert m.classification == "high"

    def test_shannon_index_math(self):
        """Shannon = -Σ p×ln(p). محصولان ٥٠/٥٠ → H = ln(2) ≈ 0.693."""
        allocs = [
            FieldAllocation("f1", "wheat", 50.0),
            FieldAllocation("f2", "barley", 50.0),
        ]
        m = compute_portfolio_metrics(allocs)
        assert abs(m.shannon_index - math.log(2)) < 0.01
        # ENC = exp(ln(2)) = 2
        assert abs(m.effective_crop_number - 2.0) < 0.01

    def test_proportions_sum_to_one(self):
        """نسب المساحة تجمع لـ١.٠ بالضبط."""
        allocs = [
            FieldAllocation("f1", "wheat", 30.0),
            FieldAllocation("f2", "barley", 45.0),
            FieldAllocation("f3", "sorghum", 25.0),
        ]
        m = compute_portfolio_metrics(allocs)
        total = sum(m.proportions.values())
        assert abs(total - 1.0) < 1e-9

    def test_empty_raises(self):
        """قائمة فارغة ترفع ValueError."""
        try:
            compute_portfolio_metrics([])
            raise AssertionError("يجب أن يرفع")
        except ValueError:
            pass

    def test_zero_area_raises(self):
        """مساحة ٠ ترفع."""
        try:
            compute_portfolio_metrics(
                [
                    FieldAllocation("f1", "wheat", 0.0),
                ]
            )
            raise AssertionError
        except ValueError:
            pass

    def test_aggregate_same_crop_multi_fields(self):
        """نفس المحصول في حقول متعدّدة → يُجمَع."""
        allocs = [
            FieldAllocation("f1", "wheat", 10.0),
            FieldAllocation("f2", "wheat", 20.0),
            FieldAllocation("f3", "barley", 30.0),
        ]
        m = compute_portfolio_metrics(allocs)
        assert m.proportions["wheat"] == 30.0 / 60.0
        assert m.proportions["barley"] == 30.0 / 60.0

    def test_suggestion_monoculture_high_risk(self):
        """monoculture → risk_level high."""
        m = compute_portfolio_metrics(
            [
                FieldAllocation("f1", "wheat", 99.0),
                FieldAllocation("f2", "barley", 1.0),
            ]
        )
        sug = suggest_for_portfolio(m)
        assert sug.risk_level == "high"
        assert "تركيز" in sug.suggestion_ar

    def test_suggestion_water_scarce_context(self):
        """water_scarce context يُغيّر الـrationale لمحفظة moderate."""
        # ٦٠/٤٠ → ENC=1.96 → moderate
        m = compute_portfolio_metrics(
            [
                FieldAllocation("f1", "wheat", 60.0),
                FieldAllocation("f2", "barley", 40.0),
            ]
        )
        assert m.classification == "moderate", f"got {m.classification}"
        sug_dry = suggest_for_portfolio(m, {"water_scarce": True})
        sug_wet = suggest_for_portfolio(m, {})
        # الـrationale يجب أن تختلف
        assert sug_dry.rationale_ar != sug_wet.rationale_ar

    def test_compare_improvement_detected(self):
        """compare يكتشف تحسّن المحفظة."""
        current = compute_portfolio_metrics(
            [
                FieldAllocation("f1", "wheat", 90.0),
                FieldAllocation("f2", "barley", 10.0),
            ]
        )
        proposed = compute_portfolio_metrics(
            [
                FieldAllocation("f1", "wheat", 60.0),
                FieldAllocation("f2", "barley", 20.0),
                FieldAllocation("f3", "sorghum", 20.0),
            ]
        )
        diff = compare_portfolios(current, proposed)
        assert diff["improved"] is True
        assert diff["enc_delta"] > 0
        assert diff["dominance_delta_pct"] < 0

    def test_format_arabic(self):
        """النصّ العربي يحوي كل المعلومات الأساسيّة."""
        m = compute_portfolio_metrics(
            [
                FieldAllocation("f1", "wheat", 60.0),
                FieldAllocation("f2", "barley", 40.0),
            ]
        )
        text = format_metrics_ar(m)
        assert "هكتار" in text
        assert "wheat" in text or "قمح" in text
        assert "٪" in text
