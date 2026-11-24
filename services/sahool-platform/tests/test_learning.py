"""Tests for the three learning components."""

from pathlib import Path

from core.learning.calibration_loop import calibrate_zone_factor
from core.learning.model_selector import ModelTier, effective_sample_size, select_model
from knowledge.conservative_rag import (
    LITERATURE_WEIGHT_CEILING,
    FieldConditions,
    KnowledgeSource,
    SourceTier,
    condition_similarity,
    retrieve,
)


class TestModelSelector:
    def test_small_data_rules_only(self):
        d = select_model(3, 1, 3)
        assert d.allowed_model == ModelTier.RULES_ONLY

    def test_pseudoreplication_caps_effective_n(self):
        # 100 records but 1 farm x 3 seasons = 3 independent units
        eff = effective_sample_size(100, 1, 3)
        assert eff == 3  # bound by independence, not raw count

    def test_ladder_progression(self):
        assert select_model(60, 10, 6).allowed_model == ModelTier.LINEAR
        assert select_model(150, 30, 5).allowed_model == ModelTier.GBOOST
        assert select_model(300, 60, 5).allowed_model == ModelTier.RF
        assert select_model(600, 120, 5).allowed_model == ModelTier.DEEP

    def test_no_deep_model_without_diverse_data(self):
        # 600 records but only 1 farm -> effective tiny -> rules only
        d = select_model(600, 1, 5)
        assert d.allowed_model == ModelTier.RULES_ONLY


class TestCalibration:
    def test_zone_factor_is_ratio_mean(self):
        zf = calibrate_zone_factor([6.0, 4.5, 5.0], [5.0, 5.0, 5.0])
        assert abs(zf - 1.033) < 0.01

    def test_no_fabrication_on_bad_input(self):
        assert calibrate_zone_factor([], []) is None
        assert calibrate_zone_factor([5.0], [0.0]) is None  # div by zero guarded


class TestConservativeRAG:
    def _field(self):
        return FieldConditions(32, "sandy", 5.5, "sorghum", "hot_arid")

    def test_matching_conditions_high_similarity(self):
        sim = condition_similarity(
            self._field(), {"crop": "sorghum", "climate_class": "hot_arid", "ece_ds_m": 5.0}
        )
        assert sim > 0.8

    def test_mismatched_conditions_low_similarity(self):
        sim = condition_similarity(
            self._field(),
            {"crop": "wheat", "climate_class": "humid_subtropical", "temp_mean_c": 22},
        )
        assert sim < 0.3

    def test_literature_weight_capped(self):
        # literature can never exceed the ceiling
        field = self._field()
        src = [
            KnowledgeSource(
                "s",
                SourceTier.LITERATURE,
                "cite",
                "txt",
                {"crop": "sorghum", "climate_class": "hot_arid"},
            )
        ]
        rk = retrieve(field, src)
        assert rk.literature_weight <= LITERATURE_WEIGHT_CEILING
        assert rk.local_weight == 0.85


class TestTabPFNTier:
    def test_very_small_data_rules_only(self):
        from core.learning.model_selector import ModelTier, select_model

        d = select_model(8, 8, 1)  # 8 farms, 1 season
        assert d.allowed_model == ModelTier.RULES_ONLY

    def test_small_data_allows_tabpfn(self):
        from core.learning.model_selector import ModelTier, select_model

        d = select_model(30, 10, 3)
        assert d.allowed_model == ModelTier.TABPFN

    def test_tabpfn_window_upper_bound(self):
        from core.learning.model_selector import ModelTier, select_model

        # at 50+ effective, should move beyond tabpfn
        d = select_model(60, 12, 5)
        assert d.allowed_model != ModelTier.TABPFN
        assert d.allowed_model != ModelTier.RULES_ONLY


class TestModelSelectorHonesty:
    """MODEL-SELECTOR-NOMINAL-SAMPLE-UNVALIDATED-01: the R² range and confidence
    are policy assumptions, never a measured result."""

    def test_every_tier_declares_unvalidated_r2_and_uncalibrated_confidence(self):
        from core.learning.model_selector import select_model

        for counts in [
            (3, 1, 3),
            (30, 10, 3),
            (60, 10, 6),
            (150, 30, 5),
            (300, 60, 5),
            (600, 120, 5),
        ]:
            d = select_model(*counts)
            assert d.r2_basis == "policy_assumption_unvalidated"
            assert d.confidence_basis == "policy_label_not_calibrated"
            assert d.measured_r2 is None

    def test_counters_alone_cannot_tell_observed_pairs_apart(self):
        # 600 records in 30 observed farm-season pairs and 600 records in 600
        # pairs share the same counters, so the selector cannot distinguish
        # them. The returned count is a nominal ceiling, not a measured N.
        from core.learning.model_selector import effective_sample_size

        assert effective_sample_size(600, 30, 20) == 600

    def test_rules_only_rationale_states_a_policy_threshold(self):
        from core.learning.model_selector import select_model

        why = select_model(3, 1, 3).rationale_ar
        assert "حدّ السياسة" in why
        assert "أي نموذج" not in why
