"""Tests for field trial design (RCBD R&D arm): control mandatory, sufficient replication,
practical significance (MDE) over statistical, high variance blocks promotion, feeds practice_promotion."""
from core.field_trial_design import design_rcbd, analyze_trial


class TestDesign:
    def test_valid_rcbd(self):
        d = design_rcbd(treatments=["صنف محلي", "صنف محسّن"], n_blocks=4)
        assert d.valid
        assert d.total_plots == 12  # 3 (مع الشاهد) × 4

    def test_control_added_automatically(self):
        d = design_rcbd(treatments=["معاملة"], n_blocks=4, include_control=True)
        assert any("شاهد" in t for t in d.treatments)

    def test_insufficient_blocks_invalid(self):
        # CRITICAL: أقلّ من 3 تكرارات → غير صالح
        d = design_rcbd(treatments=["أ", "ب"], n_blocks=2)
        assert not d.valid

    def test_too_many_treatments_warns(self):
        d = design_rcbd(treatments=["أ","ب","ج","د","هـ","و","ز"], n_blocks=4)
        assert any("يتجاوز" in w for w in d.warnings_ar)


class TestAnalysis:
    def test_meaningful_effect_signals_promotion(self):
        a = analyze_trial(treatment_results={
            "شاهد": [3.0, 3.1, 2.9, 3.0],
            "محسّن": [3.8, 3.9, 3.7, 3.85]}, mde_pct=10.0)
        assert a.best_treatment == "محسّن"
        assert a.meets_mde
        assert a.promotion_signal

    def test_small_effect_below_mde_no_promotion(self):
        # CRITICAL: فرق دون MDE عديم المغزى مهما كان "دالّاً"
        a = analyze_trial(treatment_results={
            "شاهد": [3.0, 3.0, 3.0, 3.0],
            "معاملة": [3.1, 3.05, 3.08, 3.02]}, mde_pct=10.0)
        assert not a.meets_mde
        assert not a.promotion_signal

    def test_high_variance_blocks_promotion(self):
        # CRITICAL: تباين عالٍ → لا ترقية (نتيجة غير مستقرّة)
        a = analyze_trial(treatment_results={
            "شاهد": [3.0, 3.0, 3.0],
            "معاملة": [5.0, 1.0, 4.5]}, mde_pct=10.0)
        assert not a.promotion_signal
        assert a.confidence == "low"

    def test_no_control_no_judgment(self):
        # CRITICAL: لا شاهد → لا حكم (قانون المقارنة المضادة)
        a = analyze_trial(treatment_results={"معاملة": [3.5, 3.6]}, mde_pct=10.0)
        assert a.best_treatment is None
        assert not a.promotion_signal

    def test_single_trial_caps_at_medium(self):
        # تجربة واحدة لا تبلغ high (تحتاج تكرار مواسم)
        a = analyze_trial(treatment_results={
            "شاهد": [3.0, 3.1, 2.9, 3.0],
            "محسّن": [3.8, 3.9, 3.7, 3.85]}, mde_pct=10.0)
        assert a.confidence in ("low", "medium")
        assert a.confidence != "high"

    def test_insufficient_reps_low_confidence(self):
        a = analyze_trial(treatment_results={
            "شاهد": [3.0, 3.0],
            "محسّن": [3.8, 3.9]}, mde_pct=10.0)
        assert a.confidence == "low"
