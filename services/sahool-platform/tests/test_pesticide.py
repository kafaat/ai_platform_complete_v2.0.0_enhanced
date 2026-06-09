"""Tests for pesticide safety gates: PHI binary governor, RRI precautionary indication, economic warning.
CRITICAL: RRI must NEVER authorize harvest alone — only the lab governs (food safety = red line)."""

from core.engines.pesticide import (
    PesticideGate,
    economic_warning,
    evaluate_pesticide_safety,
    phi_gate,
    predict_residue,
    residue_risk_index,
)


class TestPHIGate:
    def test_phi_not_elapsed_blocks(self):
        ok, _ = phi_gate(5, 14)
        assert ok is False

    def test_phi_elapsed_passes(self):
        ok, _ = phi_gate(15, 14)
        assert ok is True

    def test_phi_exactly_at_threshold_passes(self):
        # مضى == PHI → انقضت (الحدّ مشمول)
        ok, _ = phi_gate(14, 14)
        assert ok is True

    def test_missing_data_returns_none(self):
        assert phi_gate(None, 14)[0] is None
        assert phi_gate(5, None)[0] is None


class TestRRI:
    def test_residue_decays_over_time(self):
        # المخلّف يقلّ مع الزمن (تفكّك أُسّي)
        early = predict_residue(10.0, 0.2, 1)
        late = predict_residue(10.0, 0.2, 20)
        assert late < early

    def test_rri_none_on_missing_data(self):
        assert residue_risk_index(None, 0.2, 5, 5.0) is None
        assert residue_risk_index(10.0, 0.2, 5, 0) is None  # mrl<=0

    def test_rri_percentage_computed(self):
        rri = residue_risk_index(10.0, 0.0, 0, 5.0)  # no decay, deposit=mrl*2
        assert rri == 200.0


class TestSafetyInvariants:
    """الثوابت الحرجة للسلامة — لا تُكسَر مهما كان."""

    def test_phi_blocks_even_with_low_rri(self):
        # CRITICAL: PHI لم يمضِ → BLOCKED حتى لو RRI منخفض جداً
        d = evaluate_pesticide_safety(
            days_since_spray=2, phi_days=14, initial_deposit=1.0, decay_k=0.5, mrl=100.0
        )  # RRI ضئيل
        assert d.gate == PesticideGate.BLOCKED
        assert d.confidence == "none"

    def test_rri_never_authorizes_harvest_alone(self):
        # CRITICAL: حتى RRI منخفض بعد PHI لا يقول "آمن" — يحيل للمختبر
        d = evaluate_pesticide_safety(
            days_since_spray=20, phi_days=14, initial_deposit=1.0, decay_k=0.5, mrl=100.0
        )
        assert d.gate == PesticideGate.CLEARED_PHI
        assert "المختبر يحكم" in d.recommendation_ar or "المؤكّد" in d.requires_lab_ar

    def test_missing_data_blocks(self):
        # القاعدة الذهبية: لا بيانات → BLOCKED
        d = evaluate_pesticide_safety(days_since_spray=None, phi_days=None)
        assert d.gate == PesticideGate.BLOCKED

    def test_high_rri_after_phi_raises_caution(self):
        # مضى PHI لكن RRI≥100% → حذر + إحالة مخبرية إلزامية
        d = evaluate_pesticide_safety(
            days_since_spray=15, phi_days=14, initial_deposit=100.0, decay_k=0.01, mrl=5.0
        )
        assert d.gate == PesticideGate.CAUTION
        assert "إلزامي" in d.requires_lab_ar


class TestEconomic:
    def test_not_viable_high_cost(self):
        level, _ = economic_warning(50, 20, 10, 100, 1.0)  # cost=80, benefit=100, ratio=0.8
        assert level == "not_viable"

    def test_viable_low_cost(self):
        level, _ = economic_warning(5, 5, 0, 100, 2.0)  # cost=10, benefit=200, ratio=0.05
        assert level == "viable"

    def test_economic_is_warning_not_safety(self):
        # الاقتصاد لا يُرجع BLOCKED — تحذير فقط
        level, msg = economic_warning(50, 20, 10, 100, 1.0)
        assert level in ("not_viable", "marginal", "viable", "unknown")
