"""Tests for farmer agency: advice not orders, rejection feeds learning (Deskilling lesson)."""
from core.farmer_agency import (
    AdvisoryDecision, FarmerResponse, record_farmer_response, analyze_rejection_pattern)


class TestFarmerAgency:
    def test_recommendation_framed_as_advice(self):
        d = AdvisoryDecision("ري 50 مم", confidence="medium")
        assert d.framed_as_advice is True
        prompt = d.to_farmer_prompt()
        assert "هل توافق" in prompt
        assert "نساعد لا نأمر" in prompt

    def test_rejection_requires_reason(self):
        d = AdvisoryDecision("تسميد", confidence="low")
        d = record_farmer_response(d, FarmerResponse.REJECTED, why_rejected_ar="أمطرت")
        assert d.response == FarmerResponse.REJECTED
        assert d.why_rejected_ar == "أمطرت"

    def test_rejection_without_reason_still_recorded(self):
        d = AdvisoryDecision("x", confidence="low")
        d = record_farmer_response(d, FarmerResponse.REJECTED)
        assert d.why_rejected_ar is not None  # placeholder, never silent

    def test_modification_recorded(self):
        d = AdvisoryDecision("ري 50", confidence="medium")
        d = record_farmer_response(d, FarmerResponse.MODIFIED, modification_ar="30 مم")
        assert d.farmer_modification_ar == "30 مم"

    def test_high_rejection_signals_local_mismatch(self):
        # CHILE LESSON: repeated rejection = algorithm may not fit local context
        decisions = [record_farmer_response(AdvisoryDecision("x","low"),
                     FarmerResponse.REJECTED if i < 5 else FarmerResponse.ACCEPTED)
                     for i in range(10)]
        p = analyze_rejection_pattern("تسميد", decisions)
        assert p.rejection_rate >= 0.4
        assert "السياق المحلّي" in p.signal_ar

    def test_small_sample_no_pattern(self):
        decisions = [record_farmer_response(AdvisoryDecision("x","low"),
                     FarmerResponse.REJECTED) for _ in range(3)]
        p = analyze_rejection_pattern("x", decisions)
        assert "عيّنة صغيرة" in p.signal_ar

    def test_good_acceptance_positive_signal(self):
        decisions = [record_farmer_response(AdvisoryDecision("x","low"),
                     FarmerResponse.ACCEPTED) for _ in range(10)]
        p = analyze_rejection_pattern("x", decisions)
        assert p.rejection_rate == 0.0
