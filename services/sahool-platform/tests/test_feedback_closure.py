"""Tests for feedback_closure - preparation for future learning loop.
Principle: data readiness ≠ model readiness. We define, don't apply."""

from core.feedback_closure import (
    LagWindow,
    SuccessDefinition,
    SuccessMetric,
    assess_acceptance_bias,
    composite_success_weight_sum,
    get_success_definitions,
    is_outcome_ready_for_learning,
    known_biases,
    learning_loop_readiness,
)


class TestSuccessDefinitions:
    def test_five_metrics_defined(self):
        defs = get_success_definitions()
        assert len(defs) >= 5
        assert SuccessMetric.YIELD_WITHIN_RANGE in defs
        assert SuccessMetric.NO_SAFETY_VIOLATION in defs

    def test_weights_sum_to_one(self):
        # CRITICAL: مجموع الأوزان ≈ 1.0 لـcomposite score
        total = composite_success_weight_sum()
        assert 0.95 <= total <= 1.05

    def test_each_definition_has_reasoning(self):
        # CRITICAL: كل metric يحمل reason_ar صريحاً (لا "ML سحري")
        for _metric, definition in get_success_definitions().items():
            assert definition.reason_ar
            assert len(definition.reason_ar) > 10

    def test_safety_violation_zero_tolerance(self):
        # السلامة لا تُتخطّى — threshold = 0
        defs = get_success_definitions()
        safety = defs[SuccessMetric.NO_SAFETY_VIOLATION]
        assert safety.threshold == 0.0


class TestLagWindow:
    def test_wheat_outcome_after_minimum_lag(self):
        # توصية عمرها 100 يوم لقمح (>min_lag=90) = ready
        from datetime import datetime, timedelta

        old = (datetime.now() - timedelta(days=100)).date().isoformat()
        ready, reason = is_outcome_ready_for_learning(old, "wheat")
        assert ready
        assert "ناضجة" in reason

    def test_premature_outcome_blocked(self):
        # CRITICAL: 4 يوم لا يكفي — لا نُغذّي learning
        from datetime import datetime, timedelta

        recent = (datetime.now() - timedelta(days=4)).date().isoformat()
        ready, reason = is_outcome_ready_for_learning(recent, "wheat")
        assert not ready
        assert "غير مكتمل" in reason

    def test_stale_outcome_blocked(self):
        # CRITICAL: outcome قديم جدّاً = stale
        from datetime import datetime, timedelta

        old = (datetime.now() - timedelta(days=500)).date().isoformat()
        ready, reason = is_outcome_ready_for_learning(old, "wheat")
        assert not ready
        assert "stale" in reason

    def test_unknown_crop_no_invention(self):
        # CRITICAL: محصول غير معرّف → لا نخترع lag window
        ready, reason = is_outcome_ready_for_learning("2026-01-01", "unknown_crop")
        assert not ready
        assert "غير معروف" in reason or "لا lag window" in reason


class TestBiasAwareness:
    def test_known_biases_listed(self):
        biases = known_biases()
        # ثلاثة على الأقل
        assert len(biases) >= 3
        assert "selection_bias_skipped" in biases

    def test_low_acceptance_flags_high_risk(self):
        # CRITICAL: قبول < 70% = selection bias قوي
        result = assess_acceptance_bias(total_recommendations=100, accepted=40, skipped=60)
        assert result["bias_risk"] == "high"
        assert "⚠️" in result["summary_ar"]

    def test_high_acceptance_low_risk(self):
        result = assess_acceptance_bias(total_recommendations=100, accepted=85, skipped=15)
        assert result["bias_risk"] == "low"
        assert "✅" in result["summary_ar"]

    def test_empty_data_no_invention(self):
        # CRITICAL: لا بيانات → "unknown"، لا "good"
        result = assess_acceptance_bias(total_recommendations=0, accepted=0, skipped=0)
        assert result["bias_risk"] == "unknown"


class TestReadinessCheck:
    def test_insufficient_outcomes_blocked(self):
        readiness = learning_loop_readiness(
            completed_outcomes_count=20,  # < 50
            acceptance_rate=0.85,
            lag_window_compliance=0.90,
        )
        assert not readiness["ready_for_learning"]
        assert any("50" in b for b in readiness["blockers"])

    def test_low_acceptance_blocked(self):
        # selection bias منع التفعيل
        readiness = learning_loop_readiness(
            completed_outcomes_count=100,
            acceptance_rate=0.50,  # < 0.7
            lag_window_compliance=0.90,
        )
        assert not readiness["ready_for_learning"]

    def test_all_conditions_met_ready(self):
        # الشروط الأربعة مكتملة → ready
        readiness = learning_loop_readiness(
            completed_outcomes_count=60,
            acceptance_rate=0.80,
            lag_window_compliance=0.85,
            bias_assessment="low",
        )
        assert readiness["ready_for_learning"]
        assert "جاهز" in readiness["summary_ar"]

    def test_high_bias_blocked(self):
        readiness = learning_loop_readiness(
            completed_outcomes_count=100,
            acceptance_rate=0.80,
            lag_window_compliance=0.85,
            bias_assessment="high",
        )
        assert not readiness["ready_for_learning"]


def test_aware_issued_date_does_not_crash():
    # issued_date بمنطقة زمنيّة (+00:00) كان يرفع TypeError (aware مقابل naive).
    from core.feedback_closure import is_outcome_ready_for_learning

    ready, reason = is_outcome_ready_for_learning(
        "2026-01-01T00:00:00+00:00", "wheat", current_date="2026-06-01"
    )
    assert isinstance(ready, bool)
