"""Tests for field_lifecycle ↔ maestro bridge."""

from core.recommendation_engine import RecommendationStatus, generate_recommendation

BLOCKED_V = {
    "quality_grade": "BLOCKED",
    "blocking_observables": ["S3", "S4", "I3"],
    "missing_A": ["S3"],
}


class TestMaestroBridge:
    def test_no_choice_stays_blocked(self):
        rec = generate_recommendation(BLOCKED_V, field_state=None)
        assert rec.status == RecommendationStatus.BLOCKED

    def test_skip_gives_limited(self):
        rec = generate_recommendation(BLOCKED_V, field_state="limited")
        assert rec.status == RecommendationStatus.LIMITED
        # safety: pesticide must be flagged as blocked
        assert any("مبيد" in a for a in rec.farmer_view.alerts_ar)

    def test_request_lab_gives_pending(self):
        rec = generate_recommendation(BLOCKED_V, field_state="pending_lab")
        assert rec.status == RecommendationStatus.PENDING_LAB
        assert any("مبيد" in a for a in rec.farmer_view.alerts_ar)

    def test_limited_still_warns_pesticide_blocked(self):
        # safety invariant: even LIMITED never opens pesticides
        for fs in ("limited", "pending_lab"):
            rec = generate_recommendation(BLOCKED_V, field_state=fs)
            assert any("سلامة" in a or "مبيد" in a for a in rec.farmer_view.alerts_ar)

    def test_ready_validation_unaffected(self):
        # a non-blocked validation should still issue normally regardless of field_state
        ok_v = {"quality_grade": "OK", "blocking_observables": [], "missing_A": []}
        rec = generate_recommendation(ok_v, field_state="ready")
        assert rec.status == RecommendationStatus.ISSUED
