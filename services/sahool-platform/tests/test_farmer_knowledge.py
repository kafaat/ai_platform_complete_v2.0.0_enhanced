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
        verify_against_data(
            fk,
            data_supports=True,
            evidence={"method": "ndvi", "reference_ids": ["scene_2026_05_01"]},
            verified_by="agronomist:42",
        )
        assert fk.verification_status == VerificationStatus.CONFIRMED
        assert fk.computed_confidence == Confidence.HIGH
        assert fk.verification_evidence["reference_ids"] == ["scene_2026_05_01"]
        assert fk.verified_by == "agronomist:42"
        assert fk.to_dict()["verification_evidence"]["method"] == "ndvi"

    def test_unreferenced_support_does_not_confirm(self):
        """U07: Boolean بلا دليل مرجعيّ لا يرفع الحالة إلى «مؤكّدة» — يبقى قيد التحقّق."""
        fk = _mk(KnowledgeType.SPATIAL)
        verify_against_data(fk, data_supports=True)
        assert fk.verification_status == VerificationStatus.PENDING
        assert fk.data_agreement is True
        assert fk.verification_evidence == {"basis": "unreferenced_claim"}
        assert fk.computed_confidence != Confidence.HIGH
        # طريقة بلا مراجع أو مراجع بلا طريقة ليست دليلاً مرجعيّاً.
        verify_against_data(fk, data_supports=True, evidence={"method": "lab"})
        assert fk.verification_status == VerificationStatus.PENDING
        verify_against_data(fk, data_supports=True, evidence={"reference_ids": ["x"]})
        assert fk.verification_status == VerificationStatus.PENDING

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


class TestBlankReferencesAreNotEvidence:
    def test_whitespace_reference_ids_keep_pending(self):
        """Copilot على #1001: `reference_ids=[" "]` لا يؤكّد."""
        fk = _mk(KnowledgeType.SPATIAL)
        verify_against_data(
            fk, data_supports=True, evidence={"method": "ndvi", "reference_ids": [" "]}
        )
        assert fk.verification_status == VerificationStatus.PENDING
        verify_against_data(
            fk, data_supports=True, evidence={"method": "  ", "reference_ids": ["x"]}
        )
        assert fk.verification_status == VerificationStatus.PENDING
        verify_against_data(
            fk, data_supports=True, evidence={"method": "ndvi", "reference_ids": [" x "]}
        )
        assert fk.verification_status == VerificationStatus.CONFIRMED


class TestUnreferencedClaimKeepsTheSubmittedEvidence:
    def test_method_and_audit_fields_survive_with_the_basis_flag(self):
        """Copilot على #1001: الأساسُ يُضاف إلى الدليل المُقدَّم ولا يستبدله."""
        fk = _mk(KnowledgeType.SPATIAL)
        verify_against_data(
            fk,
            data_supports=True,
            evidence={"method": "lab", "reference_ids": [" "], "note": "sample lost"},
            verified_by="tech:9",
        )
        assert fk.verification_status == VerificationStatus.PENDING
        assert fk.verification_evidence == {
            "method": "lab",
            "reference_ids": [" "],
            "note": "sample lost",
            "basis": "unreferenced_claim",
        }
        assert fk.verified_by == "tech:9"
        # بلا دليل أصلاً ⇒ الأساس وحدَه (لا اختلاق حقول).
        bare = _mk(KnowledgeType.SPATIAL)
        verify_against_data(bare, data_supports=True)
        assert bare.verification_evidence == {"basis": "unreferenced_claim"}
