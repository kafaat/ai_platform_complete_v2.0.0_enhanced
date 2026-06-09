"""Tests for the maestro — integrated recommendation engine."""

from core.recommendation_engine import FarmerSignal, RecommendationStatus, generate_recommendation


class TestMaestro:
    def test_blocked_gives_no_recommendation(self):
        v = dict(
            quality_grade="BLOCKED",
            blocking_observables=["S3", "S4"],
            missing_A=["S3", "S4"],
            missing_B_count=0,
        )
        rec = generate_recommendation(v)
        assert rec.status == RecommendationStatus.BLOCKED
        assert rec.farmer_view.signal == FarmerSignal.UNKNOWN
        assert "لا يمكن" in rec.farmer_view.headline_ar

    def test_farmer_view_hides_backend_detail(self):
        # farmer view must NOT contain raw numbers like ET0
        class Irr:
            et0_mm = 10.0
            etc_mm = 8.0
            m3_per_ha = 350.0

        v = dict(quality_grade="MEDIUM", missing_A=[], missing_B_count=2, blocking_observables=[])
        rec = generate_recommendation(v, irrigation=Irr())
        # backend has the numbers
        assert rec.backend.et0_mm == 10.0
        # farmer headline is actionable, not a raw equation
        assert "اروِ" in rec.farmer_view.headline_ar
        assert "ET" not in rec.farmer_view.headline_ar

    def test_yield_never_fabricated(self):
        v = dict(quality_grade="MEDIUM", missing_A=[], missing_B_count=2, blocking_observables=[])
        rec = generate_recommendation(v)
        # no calibration -> yield stays null
        assert rec.predicted_yield_t_ha is None

    def test_confidence_lowered_without_calibration(self):
        v = dict(quality_grade="HIGH", missing_A=[], missing_B_count=0, blocking_observables=[])
        rec = generate_recommendation(v, zone_factor_status="pending")
        # high data but no calibration -> not high confidence
        assert rec.confidence == "medium"

    def test_unsuitable_crop_triggers_danger(self):
        class Suit:
            suitability_class = "N"

        v = dict(quality_grade="MEDIUM", missing_A=[], missing_B_count=1, blocking_observables=[])
        rec = generate_recommendation(v, suitability=Suit())
        assert rec.farmer_view.signal == FarmerSignal.DANGER
