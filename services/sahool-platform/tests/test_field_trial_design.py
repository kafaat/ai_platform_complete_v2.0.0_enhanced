"""Tests for field trial design (RCBD R&D arm): control mandatory, sufficient replication,
practical significance (MDE) over statistical, high variance blocks promotion, feeds practice_promotion."""

import pytest
from core.field_trial_design import analyze_trial, design_rcbd

pytestmark = pytest.mark.unit


class TestDesign:
    def test_valid_rcbd(self):
        d = design_rcbd(treatments=["صنف محلي", "صنف محسّن"], n_blocks=4)
        assert d.valid
        assert d.total_plots == 12  # 3 (مع الشاهد) × 4

    def test_control_added_automatically(self):
        d = design_rcbd(treatments=["معاملة"], n_blocks=4, include_control=True)
        assert any("شاهد" in t for t in d.treatments)

    @pytest.mark.parametrize("control", ["شاهد", "control", " CONTROL "])
    def test_existing_control_is_not_inserted_again(self, control):
        d = design_rcbd(treatments=[control, "معاملة"], n_blocks=4)
        assert d.valid
        assert d.treatments == [control.strip(), "معاملة"]
        assert d.total_plots == 8

    @pytest.mark.parametrize(
        "treatments",
        [
            ["شاهد", "control", "معاملة"],
            ["معاملة", " معاملة "],
            ["Treatment", "treatment"],
            [""],
            ["   "],
        ],
    )
    def test_ambiguous_or_blank_treatment_names_rejected(self, treatments):
        with pytest.raises(ValueError):
            design_rcbd(treatments=treatments, n_blocks=4)

    def test_insufficient_blocks_invalid(self):
        # CRITICAL: أقلّ من 3 تكرارات → غير صالح
        d = design_rcbd(treatments=["أ", "ب"], n_blocks=2)
        assert not d.valid

    def test_too_many_treatments_warns(self):
        d = design_rcbd(treatments=["أ", "ب", "ج", "د", "هـ", "و", "ز"], n_blocks=4)
        assert any("يتجاوز" in w for w in d.warnings_ar)

    def test_three_blocks_allowed_with_recommendation(self):
        d = design_rcbd(treatments=["معاملة"], n_blocks=3)
        assert d.valid
        assert any("4" in w for w in d.warnings_ar)


class TestAnalysis:
    def test_meaningful_effect_signals_promotion(self):
        a = analyze_trial(
            treatment_results={"شاهد": [3.0, 3.1, 2.9, 3.0], "محسّن": [3.8, 3.9, 3.7, 3.85]},
            mde_pct=10.0,
        )
        assert a.best_treatment == "محسّن"
        assert a.meets_mde
        assert a.promotion_signal

    def test_small_effect_below_mde_no_promotion(self):
        # CRITICAL: فرق دون MDE عديم المغزى مهما كان "دالّاً"
        a = analyze_trial(
            treatment_results={"شاهد": [3.0, 3.0, 3.0, 3.0], "معاملة": [3.1, 3.05, 3.08, 3.02]},
            mde_pct=10.0,
        )
        assert not a.meets_mde
        assert not a.promotion_signal

    def test_high_variance_blocks_promotion(self):
        # CRITICAL: تباين عالٍ → لا ترقية (نتيجة غير مستقرّة)
        a = analyze_trial(
            treatment_results={"شاهد": [3.0, 3.0, 3.0], "معاملة": [5.0, 1.0, 4.5]}, mde_pct=10.0
        )
        assert not a.promotion_signal
        assert a.confidence == "low"

    def test_no_control_no_judgment(self):
        # CRITICAL: لا شاهد → لا حكم (قانون المقارنة المضادة)
        a = analyze_trial(treatment_results={"معاملة": [3.5, 3.6]}, mde_pct=10.0)
        assert a.best_treatment is None
        assert not a.promotion_signal

    def test_single_trial_caps_at_medium(self):
        # تجربة واحدة لا تبلغ high (تحتاج تكرار مواسم)
        a = analyze_trial(
            treatment_results={"شاهد": [3.0, 3.1, 2.9, 3.0], "محسّن": [3.8, 3.9, 3.7, 3.85]},
            mde_pct=10.0,
        )
        assert a.confidence in ("low", "medium")
        assert a.confidence != "high"

    def test_insufficient_reps_low_confidence(self):
        a = analyze_trial(treatment_results={"شاهد": [3.0, 3.0], "محسّن": [3.8, 3.9]}, mde_pct=10.0)
        assert a.confidence == "low"

    def test_inferior_treatment_never_signals_promotion(self):
        a = analyze_trial(
            treatment_results={"شاهد": [100.0] * 4, "معاملة": [80.0] * 4},
            mde_pct=10.0,
        )
        assert a.effect_size == -20.0
        assert not a.meets_mde
        assert not a.practically_significant
        assert not a.promotion_signal
        assert "لا تتفوّق" in a.note_ar

    @pytest.mark.parametrize("control_count", [1, 3, 5])
    def test_unmatched_control_replicates_cannot_support_promotion(self, control_count):
        a = analyze_trial(treatment_results={"شاهد": [10.0] * control_count, "معاملة": [12.0] * 4})
        assert a.effect_size == 2.0  # Descriptive means remain available.
        assert a.confidence == "low"
        assert not a.promotion_signal
        assert any("غير متساوية" in w for w in a.warnings_ar)

    def test_three_valid_pairs_remain_below_promotion_policy(self):
        a = analyze_trial(treatment_results={"شاهد": [10.0] * 3, "معاملة": [12.0] * 3})
        assert a.confidence == "low"
        assert not a.promotion_signal

    def test_control_variability_blocks_unstable_difference(self):
        a = analyze_trial(treatment_results={"شاهد": [1.0, 3.0, 17.0, 19.0], "معاملة": [12.0] * 4})
        assert a.meets_mde
        assert a.confidence == "low"
        assert not a.promotion_signal
        assert any("تباين عالٍ" in w for w in a.warnings_ar)

    def test_shared_block_variation_is_removed_by_pairing(self):
        a = analyze_trial(
            treatment_results={
                "شاهد": [10.0, 30.0, 50.0, 70.0],
                "معاملة": [12.0, 32.0, 52.0, 72.0],
            },
            mde_pct=4.0,
        )
        assert a.effect_size == 2.0
        assert a.promotion_signal

    @pytest.mark.parametrize("scale", [0.0001, 1.0, 1000.0])
    @pytest.mark.parametrize(
        ("control", "treatment", "promote"),
        [
            ([5.0] * 4, [8.0, 10.0, 12.0, 14.0], True),
            ([1.0, 3.0, 17.0, 19.0], [12.0] * 4, False),
        ],
    )
    def test_screening_does_not_depend_on_measurement_unit(
        self, scale, control, treatment, promote
    ):
        a = analyze_trial(
            treatment_results={
                "شاهد": [v * scale for v in control],
                "معاملة": [v * scale for v in treatment],
            }
        )
        assert a.meets_mde
        assert a.promotion_signal is promote
        assert a.confidence == ("medium" if promote else "low")

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
    @pytest.mark.parametrize("label", ["شاهد", "معاملة"])
    def test_nonfinite_observations_rejected(self, value, label):
        results = {"شاهد": [10.0] * 4, "معاملة": [12.0] * 4}
        results[label][0] = value
        with pytest.raises(ValueError):
            analyze_trial(treatment_results=results)

    @pytest.mark.parametrize("mde", [0.0, -10.0, float("nan"), float("inf"), True])
    def test_mde_must_be_positive_and_finite(self, mde):
        with pytest.raises(ValueError):
            analyze_trial(
                treatment_results={"شاهد": [10.0] * 4, "معاملة": [12.0] * 4},
                mde_pct=mde,
            )

    @pytest.mark.parametrize("control_mean", [0.0, -10.0])
    def test_nonpositive_control_mean_has_no_relative_promotion(self, control_mean):
        a = analyze_trial(treatment_results={"شاهد": [control_mean] * 4, "معاملة": [12.0] * 4})
        assert not a.meets_mde
        assert not a.promotion_signal
        assert "غير موجب" in a.note_ar

    def test_english_control_alias_works_in_analysis(self):
        a = analyze_trial(treatment_results={" CONTROL ": [10.0] * 4, "معاملة": [12.0] * 4})
        assert a.promotion_signal

    @pytest.mark.parametrize(
        "results",
        [
            {"شاهد": [10.0] * 4, "control": [10.0] * 4, "معاملة": [12.0] * 4},
            {"شاهد": [10.0] * 4, "معاملة": [12.0] * 4, " معاملة ": [12.0] * 4},
            {"شاهد": [10.0] * 4, " ": [12.0] * 4},
        ],
    )
    def test_ambiguous_analysis_labels_rejected(self, results):
        with pytest.raises(ValueError):
            analyze_trial(treatment_results=results)
