"""Tests for structured farmer knowledge — enforcing anti-superstition guards."""

from knowledge.farmer_knowledge import (
    Confidence,
    FarmerKnowledge,
    KnowledgeType,
    VerificationStatus,
    verify_against_data,
)


def _mk(ktype, mechanism=""):
    return FarmerKnowledge(
        "t1", ktype, "نص", "001", "al_jawf", "Z1", Confidence.HIGH, mechanism_ar=mechanism
    )


class TestFarmerKnowledge:
    def test_causal_without_mechanism_rejected(self):
        """السببية بلا آلية تُرفض تلقائياً (حماية من الخرافة)."""
        fk = _mk(KnowledgeType.CAUSAL, mechanism="")
        assert fk.verification_status == VerificationStatus.REJECTED
        assert fk.prior_weight == 0.0

    def test_causal_with_mechanism_not_auto_rejected(self):
        fk = _mk(KnowledgeType.CAUSAL, mechanism="آلية فيزيائية واضحة")
        assert fk.verification_status != VerificationStatus.REJECTED

    def test_high_farmer_confidence_does_not_grant_high_system_confidence(self):
        """ثقة المزارع العالية لا تمنح ثقة نظام عالية بلا تحقّق."""
        fk = _mk(KnowledgeType.TEMPORAL)  # farmer_confidence=HIGH
        assert fk.computed_confidence != Confidence.HIGH  # pending

    def test_verification_confirmed_raises_confidence(self):
        fk = _mk(KnowledgeType.SPATIAL)
        verify_against_data(fk, data_supports=True)
        assert fk.verification_status == VerificationStatus.CONFIRMED
        assert fk.computed_confidence == Confidence.HIGH

    def test_contradiction_lowers_not_rejects(self):
        """التعارض يُسجّل للدراسة، لا يُرفض (قد يكون الحساس مخطئاً)."""
        fk = _mk(KnowledgeType.SPATIAL)
        verify_against_data(fk, data_supports=False)
        assert fk.verification_status == VerificationStatus.CONTRADICTED
        assert fk.prior_weight == 0.0  # not used until studied
        assert fk.computed_confidence == Confidence.LOW

    def test_spatial_prior_stronger_than_practice(self):
        """المكانية أقوى prior من الممارسة (أقل عرضة للتحيّز)."""
        spatial = _mk(KnowledgeType.SPATIAL)
        practice = _mk(KnowledgeType.PRACTICE)
        assert spatial.prior_weight > practice.prior_weight

    def test_rejected_stays_rejected_after_verify(self):
        fk = _mk(KnowledgeType.CAUSAL, mechanism="")  # rejected
        verify_against_data(fk, data_supports=True)
        assert fk.verification_status == VerificationStatus.REJECTED


class TestConservativeWeight:
    def test_weight_never_exceeds_ceiling(self):
        from knowledge.farmer_knowledge import (
            COMMUNITY_WEIGHT_CEILING,
            Confidence,
            FarmerKnowledge,
            KnowledgeType,
            VerificationStatus,
        )

        # even the strongest case (spatial + confirmed) stays under ceiling
        fk = FarmerKnowledge(
            "x",
            KnowledgeType.SPATIAL,
            "c",
            "t",
            "r",
            "s",
            Confidence.HIGH,
            mechanism_ar="m",
            verification_status=VerificationStatus.CONFIRMED,
            data_agreement=True,
        )
        assert fk.prior_weight <= COMMUNITY_WEIGHT_CEILING

    def test_zero_weight_on_governing(self):
        from knowledge.farmer_knowledge import (
            Confidence,
            FarmerKnowledge,
            KnowledgeType,
            VerificationStatus,
            applicable_weight,
        )

        fk = FarmerKnowledge(
            "x",
            KnowledgeType.SPATIAL,
            "c",
            "t",
            "r",
            "s",
            Confidence.HIGH,
            mechanism_ar="m",
            verification_status=VerificationStatus.CONFIRMED,
            data_agreement=True,
        )
        # knowledge must NEVER override governing/physics — golden rule
        for obs in ["S3", "S4", "I3", "L3", "ETc", "ET0"]:
            assert applicable_weight(fk, obs) == 0.0

    def test_weight_applies_on_non_governing(self):
        from knowledge.farmer_knowledge import (
            Confidence,
            FarmerKnowledge,
            KnowledgeType,
            VerificationStatus,
            applicable_weight,
        )

        fk = FarmerKnowledge(
            "x",
            KnowledgeType.SPATIAL,
            "c",
            "t",
            "r",
            "s",
            Confidence.HIGH,
            verification_status=VerificationStatus.PENDING,
        )
        # on a non-governing target (e.g. sampling priority) weight applies
        assert applicable_weight(fk, "sampling_priority") > 0.0
